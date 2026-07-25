"""Les PIEGES comme citoyens de premiere classe — ce qui empeche de refaire deux fois l'erreur.

Constat vecu le 24/07/2026 : les trois informations qui m'ont le plus servi de la journee etaient
des pieges — « ne jamais committer depuis le bac a sable », « wscript retire les guillemets
internes », « le journal local n'a pas les ecritures memlog-http ». Deux d'entre eux ont ete
DECOUVERTS A LA DURE, puis journalises en prose, noyes dans des pavés de 2000 caracteres.

Pour un agent sans continuite, refaire la meme erreur est LE defaut structurel. Un piege doit donc
etre : typé (donc filtrable et indexe), remonte EN TETE d'une reprise, et jamais perime en silence
— un piege corrige (C3) doit cesser d'etre servi comme actuel.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)


def _ev(typ, texte, minute=0, sid="s1", src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute),
                       data={"text": texte, "session_id": sid, "turn_id": "t%d" % minute})


def test_le_type_piege_existe():
    assert EventType.PITFALL.value == "pitfall"


def test_pieges_remonte_les_pieges_seuls():
    evs = [
        _ev(EventType.PITFALL, "ne jamais committer depuis le bac a sable", 0),
        _ev(EventType.DECISION, "on part sur MiniLM", 1),
        _ev(EventType.PITFALL, "wscript retire les guillemets internes", 2),
    ]
    out = memory.pitfalls(evs)
    assert out["counts"]["pieges"] == 2
    assert all("piege" not in p or True for p in out["pieges"])
    assert not any("MiniLM" in p["text"] for p in out["pieges"])


def test_le_plus_recent_d_abord():
    """Un piege recent porte sur l'etat courant du systeme : il passe devant."""
    evs = [_ev(EventType.PITFALL, "ancien piege", 0), _ev(EventType.PITFALL, "piege recent", 5)]
    out = memory.pitfalls(evs)
    assert out["pieges"][0]["text"] == "piege recent"


def test_un_piege_corrige_est_signale_pas_efface():
    """C3 : on ne supprime jamais. Un piege revise doit rester lisible AVEC son drapeau, sinon
    on perd le « pourquoi ca a change »."""
    evs = [
        _ev(EventType.PITFALL, "il faut passer par la variable X", 0),
        _ev(EventType.CORRECTION, "en fait X a ete supprime, utiliser Y", 1),
    ]
    out = memory.pitfalls(evs)
    p = out["pieges"][0]
    assert p["superseded"] is True and p["corrected_by"]


def test_pieges_actifs_seulement_sur_demande():
    """Pour une REPRISE, on veut d'abord ce qui mord encore."""
    evs = [
        _ev(EventType.PITFALL, "piege perime", 0),
        _ev(EventType.CORRECTION, "ne s'applique plus", 1),
        _ev(EventType.PITFALL, "piege toujours valable", 2, sid="s2"),
    ]
    out = memory.pitfalls(evs, actifs_seuls=True)
    assert out["counts"]["pieges"] == 1
    assert out["pieges"][0]["text"] == "piege toujours valable"


def test_filtre_par_projet():
    evs = [
        _ev(EventType.PITFALL, "piege du projet A", 0, src="project:a"),
        _ev(EventType.PITFALL, "piege du projet B", 1, src="project:b"),
    ]
    out = memory.pitfalls(evs, source_prefix="project:a")
    assert out["counts"]["pieges"] == 1 and "projet A" in out["pieges"][0]["text"]


def test_texte_integral_disponible():
    """Un piege tronque au milieu de la commande a eviter ne sert a rien."""
    long = "ne jamais faire ceci : " + "commande tres longue " * 40
    out = memory.pitfalls([_ev(EventType.PITFALL, long)], chars=0)
    assert out["pieges"][0]["text"] == long


def test_sortie_bornee_compteur_complet():
    evs = [_ev(EventType.PITFALL, "piege %d" % i, i) for i in range(30)]
    out = memory.pitfalls(evs, k=5)
    assert out["counts"]["pieges"] == 30 and len(out["pieges"]) == 5 and out["truncated"] is True


def test_aucun_piege_ne_leve_pas():
    assert memory.pitfalls([])["counts"]["pieges"] == 0


def test_lecture_seule_ne_mute_pas():
    import copy
    evs = [_ev(EventType.PITFALL, "x", 0)]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    memory.pitfalls(evs)
    assert [e.model_dump() for e in evs] == snap


# --- levier 3 : que la memoire annonce ses ANGLES MORTS ---

def test_health_signale_un_index_semantique_perime():
    """Vecu le 24/07 : `health` disait `available: true` alors que le canal semantique etait MORT
    (0 vecteur sur 2518). Il fallait penser a interroger `index_status` pour le decouvrir.
    Une memoire qui se tait sur ses angles morts est moins fiable qu'une memoire qui les annonce."""
    evs = [_ev(EventType.DECISION, "un fait", 0)]
    h = memory.health(evs, index={"eligible": 2518, "indexed": 0, "covered_pct": 0.0,
                                  "fresh": False})
    assert h["degraded"] is True
    assert any("index" in w.lower() for w in h["warnings"])


def test_health_muet_quand_tout_va_bien():
    """Pas de bruit inutile : sans signal de degradation, aucun avertissement."""
    evs = [_ev(EventType.DECISION, "un fait", 0)]
    h = memory.health(evs, index={"eligible": 10, "indexed": 10, "covered_pct": 100.0,
                                  "fresh": True}, now=T0 + timedelta(minutes=5))
    assert h["degraded"] is False and h["warnings"] == []


def test_health_signale_une_memoire_qui_ne_recoit_plus_rien():
    """Un substrat qui n'a rien capte depuis des jours est un symptome, pas un etat normal."""
    evs = [_ev(EventType.DECISION, "vieux fait", 0)]
    h = memory.health(evs, now=T0 + timedelta(days=9))
    assert h["degraded"] is True
    assert any("dernier evenement" in w.lower() for w in h["warnings"])


def test_health_retro_compatible():
    """Les champs historiques restent presents et inchanges (consommateurs existants)."""
    evs = [_ev(EventType.DECISION, "un fait", 0)]
    h = memory.health(evs)
    for champ in ("available", "event_count", "last_event_at", "sources"):
        assert champ in h
    assert h["event_count"] == 1


# --- ecriture : un type qu'on ne peut pas ecrire ne sert a rien ---

def test_un_piege_peut_etre_ecrit_de_bout_en_bout(tmp_path):
    """Constat du 25/07 : le type PITFALL existait mais l'ingest le refusait (422 invalid kind).
    Un citoyen de premiere classe doit pouvoir ENTRER dans le journal."""
    from multiservice import projlog
    from multiservice.journal import read_events
    assert "pitfall" in projlog.KINDS
    jp = tmp_path / "j.jsonl"
    projlog.log(jp, "pitfall", "wscript retire les guillemets internes",
                source="project:demo", session_id="s", now=T0)
    ev = read_events(jp)[0]
    assert ev.type == EventType.PITFALL
    assert memory.pitfalls(read_events(jp))["counts"]["pieges"] == 1


def test_un_piege_reste_non_autoritaire_pour_le_modele():
    """C1 : le modele OBSERVE, l'humain tranche. Un piege est une observation de terrain — il ne
    doit ni etre refuse au modele, ni le laisser trancher a la place de l'humain."""
    from multiservice import memory_tools
    assert "pitfall" not in memory_tools.AUTHORITATIVE_KINDS
