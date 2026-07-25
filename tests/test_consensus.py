"""V3 — PROTOCOLE INTER-AGENTS : une conversation, pas quatre monologues.

Constat (25/07/2026) : quatre sources ecrivent deja dans le meme journal — Claude, ChatGPT (37 %
du corpus), Ollama, l'humain — et **personne ne repond a personne**. Chacun depose ses faits a
cote de ceux des autres. Un fait dit une fois par un agent a exactement le meme poids qu'un fait
verifie par trois.

Trois relations, sur le patron deja etabli par `closes` et `rates` :

    data.confirms = [ids]      data.contradicts = [ids]      data.refines = [ids]

Ce qui fait la valeur, ce n'est pas le NOMBRE de confirmations : c'est la DIVERSITE des sources.
Trois confirmations du meme agent ne valent pas trois agents independants — sinon un agent
bavard fabriquerait de la certitude tout seul.

Et une contradiction ne clot RIEN : elle remonte comme « a trancher ». L'humain arbitre (C1).
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, src="project:demo", **data_extra):
    data = {"text": texte, "session_id": "s1", "turn_id": "t%d" % minute}
    data.update(data_extra)
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute), data=data)


def test_une_confirmation_est_comptee_avec_sa_source():
    fait = _ev(EventType.DECISION, "MiniLM suffit", 0, src="project:claude")
    conf = _ev(EventType.OBSERVATION, "verifie de mon cote", 1, src="project:chatgpt",
               confirms=[fait.id])
    c = memory.consensus([fait, conf])[fait.id]
    assert c["confirms"] == ["project:chatgpt"]


def test_la_diversite_des_sources_compte_pas_le_nombre():
    """LE point de V3 : un agent bavard ne doit pas fabriquer de la certitude tout seul."""
    fait = _ev(EventType.DECISION, "x", 0, src="project:claude")
    trois_fois_le_meme = [_ev(EventType.OBSERVATION, "ok", i, src="project:chatgpt",
                              confirms=[fait.id]) for i in (1, 2, 3)]
    c = memory.consensus([fait] + trois_fois_le_meme)[fait.id]
    assert c["agents_confirmants"] == 1        # trois retours, UNE source


def test_deux_agents_distincts_valent_deux():
    fait = _ev(EventType.DECISION, "x", 0, src="project:claude")
    evs = [fait,
           _ev(EventType.OBSERVATION, "ok", 1, src="project:chatgpt", confirms=[fait.id]),
           _ev(EventType.OBSERVATION, "ok", 2, src="project:ollama", confirms=[fait.id])]
    assert memory.consensus(evs)[fait.id]["agents_confirmants"] == 2


def test_un_agent_ne_se_confirme_pas_lui_meme():
    """Se confirmer soi-meme n'apporte aucune information : la relation est ecartee, donc le fait
    n'a AUCUNE relation et n'apparait pas — l'absence de signal n'est pas un signal."""
    fait = _ev(EventType.DECISION, "x", 0, src="project:claude")
    auto = _ev(EventType.OBSERVATION, "je confirme", 1, src="project:claude",
               confirms=[fait.id])
    assert fait.id not in memory.consensus([fait, auto])


def test_une_contradiction_est_signalee():
    fait = _ev(EventType.DECISION, "bge-m3 est indispensable", 0, src="project:claude")
    contre = _ev(EventType.OBSERVATION, "mesure inverse", 1, src="project:chatgpt",
                 contradicts=[fait.id])
    c = memory.consensus([fait, contre])[fait.id]
    assert c["contradicts"] == ["project:chatgpt"]


def test_une_contradiction_remonte_comme_a_trancher():
    fait = _ev(EventType.DECISION, "bge-m3 est indispensable", 0, src="project:claude")
    contre = _ev(EventType.OBSERVATION, "mesure inverse", 1, src="project:chatgpt",
                 contradicts=[fait.id])
    ouvertes = memory.contradictions_ouvertes([fait, contre])
    assert len(ouvertes) == 1
    assert ouvertes[0]["id"] == fait.id and "project:chatgpt" in ouvertes[0]["contredit_par"]


def test_une_contradiction_tranchee_n_est_plus_ouverte():
    """C3 : trancher, c'est clore le fait depasse — jamais le supprimer."""
    fait = _ev(EventType.DECISION, "bge-m3 est indispensable", 0, src="project:claude")
    contre = _ev(EventType.OBSERVATION, "mesure inverse", 1, src="project:chatgpt",
                 contradicts=[fait.id])
    arbitrage = _ev(EventType.CORRECTION, "tranche : MiniLM suffit", 2, src="project:local")
    arbitrage.data["closes"] = [fait.id]
    assert memory.contradictions_ouvertes([fait, contre, arbitrage]) == []


def test_une_contradiction_ne_clot_rien_toute_seule():
    """C1 : la memoire observe, l'humain tranche. Un agent ne peut pas perimer le fait d'un autre."""
    fait = _ev(EventType.DECISION, "x", 0, src="project:claude")
    contre = _ev(EventType.OBSERVATION, "non", 1, src="project:chatgpt", contradicts=[fait.id])
    actifs = {e.id for e in memory.as_of([fait, contre])}
    assert fait.id in actifs


def test_une_precision_est_distinguee_d_une_contradiction():
    """Preciser n'est pas contredire : le fait reste vrai, il gagne du contexte."""
    fait = _ev(EventType.DECISION, "MiniLM suffit", 0, src="project:claude")
    prec = _ev(EventType.OBSERVATION, "en 384d, pas en 256", 1, src="project:ollama",
               refines=[fait.id])
    c = memory.consensus([fait, prec])[fait.id]
    assert c["refines"] == ["project:ollama"] and not c["contradicts"]


def test_recall_expose_le_consensus():
    fait = _ev(EventType.DECISION, "index vectoriel binaire", 0, src="project:claude")
    conf = _ev(EventType.OBSERVATION, "confirme", 1, src="project:chatgpt", confirms=[fait.id])
    hits = memory.recall([fait, conf], "vectoriel")
    assert hits[0]["consensus"]["agents_confirmants"] == 1


def test_un_fait_sans_relation_n_alourdit_pas_la_sortie():
    fait = _ev(EventType.DECISION, "index vectoriel binaire", 0)
    assert "consensus" not in memory.recall([fait], "vectoriel")[0]


def test_lecture_seule_ne_mute_pas():
    import copy
    fait = _ev(EventType.DECISION, "x", 0, src="project:claude")
    evs = [fait, _ev(EventType.OBSERVATION, "ok", 1, src="project:chatgpt", confirms=[fait.id])]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    memory.consensus(evs)
    assert [e.model_dump() for e in evs] == snap


# --- la boucle se ferme : arriver SOUS LES YEUX et pouvoir etre ECRIT ---

def test_resume_remonte_les_contradictions_a_trancher():
    """Un desaccord entre agents qui n'arrive jamais sous les yeux n'est pas arbitre : il
    pourrit. C'est le seul endroit ou l'humain peut trancher (C1)."""
    fait = _ev(EventType.DECISION, "bge-m3 est indispensable", 0, src="project:demo")
    contre = _ev(EventType.OBSERVATION, "mesure inverse", 1, src="project:chatgpt",
                 contradicts=[fait.id])
    r = memory.resume([fait, contre], "project:demo", now=T0 + timedelta(days=1))
    assert r["a_trancher"] and r["a_trancher"][0]["id"] == fait.id
    assert r["counts"]["a_trancher"] == 1


def test_sans_desaccord_la_reprise_ne_fait_pas_de_bruit():
    fait = _ev(EventType.DECISION, "un fait", 0, src="project:demo")
    r = memory.resume([fait], "project:demo", now=T0 + timedelta(days=1))
    assert r["a_trancher"] == [] and r["counts"]["a_trancher"] == 0


def test_une_relation_peut_etre_ecrite(tmp_path):
    from multiservice import projlog
    from multiservice.journal import read_events
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "observation", "je confirme de mon cote", source="project:chatgpt",
                session_id="s", confirms=["id-cible"])
    assert read_events(jp)[0].data["confirms"] == ["id-cible"]


def test_l_ingest_valide_les_relations():
    from multiservice import ingest
    assert ingest.valider_champs_structures({"confirms": ["abc"]}) is None
    r = ingest.valider_champs_structures({"contradicts": "abc"})     # chaine au lieu de liste
    assert r is not None and "contradicts" in r["error"]
