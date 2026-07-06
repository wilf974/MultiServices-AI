"""project_review(project) : vue composée par PROJET (source), bi-temporelle, LECTURE SEULE.

Compose l'existant (lessons/standing) + décisions corrigées / hypothèses réfutées / validations.
Sortie bornée (économie de sortie : compteurs complets, `truncated`). Ne mute rien.
"""
import copy
from datetime import datetime, timezone, timedelta

from multiservice.events import AetherEvent, EventType
from multiservice.memory import project_review

T0 = datetime(2026, 6, 1, 12, 0, tzinfo=timezone.utc)
NOW = datetime(2026, 7, 6, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid, src="project:demo"):
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def _journal():
    return [
        # décision corrigée (même session -> supersede C3)
        _ev(EventType.DECISION, "utiliser un moteur NEMA-17", T0, "arch"),
        _ev(EventType.CORRECTION, "en fait un servo MG996R (le NEMA calait)", T0 + timedelta(days=1), "arch"),
        # décision valide (debout)
        _ev(EventType.DECISION, "MCP en lecture seule", T0, "constitution"),
        # hypothèse réfutée
        _ev(EventType.HYPOTHESIS, "la diversite cause la survie spatiale", T0, "hyp"),
        _ev(EventType.CORRECTION, "refute : effet fonctionnel, pas spatial", T0 + timedelta(days=2), "hyp"),
        # hypothèse debout
        _ev(EventType.HYPOTHESIS, "le cache reduit les tokens", T0, "hyp2"),
        # validation
        _ev(EventType.VALIDATION, "349 tests verts", T0, "ci"),
        # AUTRE projet -> doit etre exclu
        _ev(EventType.DECISION, "hors scope total", T0, "x", src="project:autre"),
    ]


def test_sections_bi_temporelles_par_projet():
    r = project_review(_journal(), "project:demo", now=NOW)
    c = r["counts"]
    assert c["decisions_valides"] == 1
    assert c["decisions_corrigees"] == 1
    assert c["hypotheses_refutees"] == 1
    assert c["hypotheses_debout"] == 1
    assert c["validations"] == 1
    assert c["lecons"] == 2                                  # 2 corrections
    # contenus
    assert any("MCP" in d["text"] for d in r["decisions_valides"])
    corr = r["decisions_corrigees"][0]
    assert "NEMA-17" in corr["text"] and corr["corrected_by"]   # pointe la correction
    assert any("spatial" in h["text"] for h in r["hypotheses_refutees"])
    assert any("cache" in h["text"] for h in r["hypotheses_debout"])


def test_isole_le_projet_rien_ne_fuit():
    r = project_review(_journal(), "project:demo", now=NOW)
    blob = str(r)
    assert "hors scope total" not in blob                    # l'autre projet est exclu


def test_lecture_seule_ne_mute_pas():
    evs = _journal()
    snap = copy.deepcopy([e.model_dump() for e in evs])
    project_review(evs, "project:demo", now=NOW)
    assert [e.model_dump() for e in evs] == snap


def test_sortie_bornee_compteurs_complets():
    evs = []
    for i in range(30):                                      # 30 validations valides
        evs.append(_ev(EventType.VALIDATION, f"validation {i}", T0 + timedelta(minutes=i), f"s{i}"))
    r = project_review(evs, "project:demo", now=NOW, k=10)
    assert r["counts"]["validations"] == 30                  # compteur COMPLET
    assert len(r["validations"]) == 10                       # sortie BORNEE
    assert r["truncated"] is True


def test_fenetre_days_ne_garde_que_le_recent():
    evs = [
        _ev(EventType.VALIDATION, "vieille validation", NOW - timedelta(days=40), "vieux"),
        _ev(EventType.VALIDATION, "validation recente", NOW - timedelta(days=2), "frais"),
    ]
    r = project_review(evs, "project:demo", days=30, now=NOW)
    assert r["counts"]["validations"] == 1
    assert r["validations"][0]["text"] == "validation recente"
