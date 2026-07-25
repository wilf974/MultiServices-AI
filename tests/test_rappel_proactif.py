"""V1 — RAPPEL PROACTIF : la memoire s'impose au bon moment, au lieu d'attendre une requete.

Le constat qui ouvre l'acte III (25/07/2026) : le piege « builder n'est pas redeployer » etait
dans la memoire UNE HEURE avant que l'erreur soit commise. Il n'a arrete personne — il a fallu
constater l'echec, puis penser a aller voir. **La memoire avait la reponse et est restee muette.**

Ici : etant donne une commande sur le point d'etre lancee, quels pieges connus mordent ?

Contraintes non negociables :
  - RAPIDE : le rappel s'intercale avant une action, il ne doit pas se faire sentir ;
  - SILENCIEUX quand rien ne mord : un garde-fou qui crie tout le temps n'est plus lu ;
  - il AVERTIT, il ne bloque pas : la memoire observe, elle ne juge ni n'agit (C1).
"""
from datetime import datetime, timedelta, timezone

from multiservice import rappel
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 25, 12, 0, tzinfo=timezone.utc)


def _piege(texte, minute=0, src="project:demo", **structure):
    data = {"text": texte, "session_id": "s1", "turn_id": "t%d" % minute}
    data.update({k: v for k, v in structure.items() if v})
    return AetherEvent(type=EventType.PITFALL, title="pitfall", description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute), data=data)


CORPUS = [
    _piege("Redemarrer un conteneur ne redeploie PAS le code quand celui-ci est DANS l image "
           "(mem-mcp, mem-ingest) : seul le journal est monte. Remede : docker build puis "
           "docker run, pas docker restart."),
    _piege("Ne jamais git commit depuis le bac a sable Linux : le montage tronque les fichiers "
           "que Claude vient d editer.", 1),
    _piege("wscript RETIRE les guillemets internes des arguments.", 2),
]


def test_une_commande_qui_mord_declenche_le_piege():
    hits = rappel.pieges_pour_commande(CORPUS, "docker restart mem-ingest")
    assert hits and "redeploie PAS" in hits[0]["text"]


def test_une_commande_anodine_ne_declenche_rien():
    """Un garde-fou qui crie tout le temps n'est plus lu."""
    assert rappel.pieges_pour_commande(CORPUS, "ls -la") == []
    assert rappel.pieges_pour_commande(CORPUS, "pytest -q") == []


def test_le_bon_piege_et_pas_les_autres():
    hits = rappel.pieges_pour_commande(CORPUS, "git commit -m 'wip'")
    assert len(hits) == 1 and "bac a sable" in hits[0]["text"]


def test_plusieurs_pieges_possibles_sont_tous_rendus():
    hits = rappel.pieges_pour_commande(CORPUS, "docker build -t mem-ingest . && docker restart x")
    assert len(hits) >= 1


def test_les_mots_vides_ne_declenchent_pas():
    """« le », « pas », « ne » sont partout : ils feraient tout matcher."""
    assert rappel.pieges_pour_commande(CORPUS, "echo le pas ne dans") == []


def test_seuls_les_pieges_sont_consultes():
    """Une decision n'est pas un garde-fou : on n'interrompt personne pour l'annoncer."""
    from multiservice.events import EventType as ET
    decision = AetherEvent(type=ET.DECISION, title="decision", description="on utilise docker",
                           source="project:demo", observed_at=T0,
                           data={"text": "on utilise docker restart partout", "session_id": "s"})
    assert rappel.pieges_pour_commande([decision], "docker restart x") == []


def test_filtre_par_projet():
    autre = _piege("piege d un autre projet avec docker", 3, src="project:autre")
    hits = rappel.pieges_pour_commande(CORPUS + [autre], "docker restart x",
                                       source_prefix="project:demo")
    assert all("autre projet" not in h["text"] for h in hits)


def test_message_lisible_et_borne():
    """Le message s'affiche dans un flux d'outil : court, actionnable, sans bruit."""
    hits = rappel.pieges_pour_commande(CORPUS, "docker restart mem-ingest")
    msg = rappel.format_avertissement(hits)
    assert "PIEGE" in msg.upper()
    assert len(msg.splitlines()) <= 12


def test_aucun_piege_donne_un_message_vide():
    assert rappel.format_avertissement([]) == ""


def test_lecture_seule_ne_mute_pas():
    import copy
    snap = copy.deepcopy([e.model_dump() for e in CORPUS])
    rappel.pieges_pour_commande(CORPUS, "docker restart x")
    assert [e.model_dump() for e in CORPUS] == snap


def test_le_message_reste_en_ascii_pur():
    """Regle du projet : sortie console en ASCII. Un tiret cadratin sort en mojibake sous
    PowerShell (constate le 25/07) — et un avertissement illisible n'avertit personne."""
    msg = rappel.format_avertissement(rappel.pieges_pour_commande(CORPUS, "docker restart x"))
    surplus = [c for c in msg if ord(c) > 127]
    assert not surplus, "caracteres non-ASCII dans le message : %r" % surplus[:5]
