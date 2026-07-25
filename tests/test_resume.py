"""`resume(projet)` — reprendre un projet en UN appel.

Constat vecu le 24/07/2026 : pour comprendre ou on en etait, il a fallu enchainer `health`,
`recent`, `brief`, `recall`, `project_review`, plus CLAUDE.md, DECISIONS.md et `git log`. Une
dizaine d'aller-retours avant d'ecrire la premiere ligne utile.

Toutes les briques existaient deja. Ce qui manquait, c'est la COMPOSITION — et surtout l'ORDRE :
ce qui mord d'abord (pieges), ce qui est degrade ensuite (sante), puis l'etat, puis le mouvement
recent. Une vue de reprise n'est pas un dump : c'est une hierarchie d'attention.

LECTURE SEULE, PURE, bornee. Ne devine rien, ne juge rien : compose l'observe.
"""
from datetime import datetime, timedelta, timezone

from multiservice import memory
from multiservice.events import AetherEvent, EventType

T0 = datetime(2026, 7, 1, 12, 0, tzinfo=timezone.utc)
NOW = T0 + timedelta(days=2)


def _ev(typ, texte, minute=0, sid="s1", src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=texte, source=src,
                       observed_at=T0 + timedelta(minutes=minute),
                       data={"text": texte, "session_id": sid, "turn_id": "t%d" % minute})


def _journal():
    return [
        _ev(EventType.PITFALL, "ne jamais committer depuis le bac a sable", 0),
        _ev(EventType.DECISION, "on part sur MiniLM 384d", 1),
        _ev(EventType.DECISION, "index binaire", 2),
        _ev(EventType.CORRECTION, "en fait le jsonl pesait 5x trop", 3),
        _ev(EventType.VALIDATION, "553 tests verts", 4),
        _ev(EventType.DECISION, "hors sujet", 5, src="project:autre"),
    ]


def test_un_seul_appel_rend_les_sections_d_une_reprise():
    r = memory.resume(_journal(), "project:demo", now=NOW)
    for section in ("projet", "as_of", "sante", "pieges", "etat", "recent", "revisions"):
        assert section in r, section


def test_les_pieges_passent_devant():
    """Ce qui a deja coute une erreur se lit AVANT le reste : c'est l'ordre qui fait la valeur."""
    r = memory.resume(_journal(), "project:demo", now=NOW)
    assert list(r).index("pieges") < list(r).index("etat")
    assert r["pieges"][0]["text"].startswith("ne jamais committer")


def test_isole_le_projet():
    r = memory.resume(_journal(), "project:demo", now=NOW)
    assert "hors sujet" not in str(r)


def test_l_etat_reprend_les_compteurs_de_la_revue():
    r = memory.resume(_journal(), "project:demo", now=NOW)
    attendu = memory.project_review(_journal(), "project:demo", now=NOW)["counts"]
    assert r["etat"]["counts"] == attendu


def test_la_sante_remonte_les_angles_morts():
    r = memory.resume(_journal(), "project:demo", now=NOW,
                      index={"eligible": 100, "indexed": 0, "covered_pct": 0.0, "fresh": False})
    assert r["sante"]["degraded"] is True
    assert any("index" in w.lower() for w in r["sante"]["warnings"])


def test_les_revisions_disent_ce_qui_a_change():
    """« Ce qui a change » est la premiere question d'une reprise apres une absence."""
    r = memory.resume(_journal(), "project:demo", now=NOW)
    assert r["revisions"] and "jsonl" in str(r["revisions"])


def test_sortie_bornee_et_texte_integral_a_la_demande():
    long = "decision tres detaillee. " * 60
    evs = [_ev(EventType.DECISION, long, i) for i in range(10)]
    borne = memory.resume(evs, "project:demo", now=NOW, k=3)
    assert len(borne["recent"]) <= 3
    entier = memory.resume(evs, "project:demo", now=NOW, k=1, chars=0)
    assert entier["recent"][0]["text"] == long


def test_projet_vide_ne_leve_pas():
    r = memory.resume([], "project:inconnu", now=NOW)
    assert r["etat"]["counts"]["decisions_valides"] == 0 and r["pieges"] == []


def test_lecture_seule_ne_mute_pas():
    import copy
    evs = _journal()
    snap = copy.deepcopy([e.model_dump() for e in evs])
    memory.resume(evs, "project:demo", now=NOW)
    assert [e.model_dump() for e in evs] == snap
