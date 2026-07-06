"""Memory Intelligence #1 — lessons_learned : lecons tirees des corrections C3.

Contrat : une lecon = une correction + les faits anterieurs de SA session qu'elle perime ;
`still_standing` = les decisions encore valides (non corrigees). PUR, lecture seule ;
VIDE tant qu'aucune correction (calibre sur l'observe, pas invente).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
import copy
from datetime import datetime, timedelta, timezone

from multiservice.events import AetherEvent, EventType
from multiservice.memory import lessons_learned

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _ev(typ, text, vf, sid, src="project:local"):
    return AetherEvent(type=typ, title=typ.value, description=text, source=src,
                       observed_at=vf, data={"text": text, "session_id": sid, "turn_id": "t"})


def test_vide_sans_correction():
    evs = [_ev(EventType.DECISION, "Licence MIT", T0, "licence")]
    out = lessons_learned(evs)
    assert out["counts"]["lessons"] == 0
    assert out["counts"]["still_standing"] == 1       # la decision tient (non corrigee)


def test_lecon_pointe_la_decision_perimee():
    evs = [
        _ev(EventType.DECISION, "Licence MIT", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0 (brevet)", T0 + timedelta(hours=1), "licence"),
        _ev(EventType.DECISION, "MCP en lecture seule", T0, "constitution"),   # non corrigee
    ]
    out = lessons_learned(evs)
    assert out["counts"]["lessons"] == 1
    lesson = out["lessons"][0]
    assert "Apache" in lesson["correction"]
    assert any("MIT" in s["text"] for s in lesson["superseded"])   # MIT abandonnee
    # la decision MIT n'est plus "still standing" ; la constitution oui
    sessions_still = {d["session"] for d in out["still_standing"]}
    assert "constitution" in sessions_still and "licence" not in sessions_still


def test_correction_scopee_a_sa_session():
    evs = [
        _ev(EventType.DECISION, "Decision A", T0, "sujet-A"),
        _ev(EventType.CORRECTION, "revise B", T0 + timedelta(hours=1), "sujet-B"),
    ]
    out = lessons_learned(evs)
    # la correction de sujet-B ne perime PAS la decision de sujet-A
    assert out["lessons"][0]["superseded"] == []
    assert any(d["session"] == "sujet-A" for d in out["still_standing"])


def test_dedup_corrections_identiques():
    """Doublon (meme session + meme texte de correction) -> une seule lecon en sortie."""
    evs = [
        _ev(EventType.DECISION, "Licence MIT", T0, "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0 + timedelta(hours=1), "licence"),
        _ev(EventType.CORRECTION, "En fait Apache-2.0", T0 + timedelta(hours=2), "licence"),  # doublon
    ]
    out = lessons_learned(evs)
    assert out["counts"]["lessons"] == 1


def test_lessons_est_pur():
    evs = [
        _ev(EventType.DECISION, "Licence MIT", T0, "licence"),
        _ev(EventType.CORRECTION, "Apache-2.0", T0 + timedelta(hours=1), "licence"),
    ]
    snap = copy.deepcopy([e.model_dump() for e in evs])
    lessons_learned(evs)
    assert [e.model_dump() for e in evs] == snap


# --- Economie de sortie (crise reelle : lessons() ~80 Ko sur le journal central) ---

def _many_lessons(n):
    """n sessions, chacune : 1 decision puis 1 correction (i croissant = plus recent)."""
    evs = []
    for i in range(n):
        sid = f"s{i}"
        evs.append(_ev(EventType.DECISION, f"decision {i}", T0 + timedelta(minutes=i), sid))
        evs.append(_ev(EventType.CORRECTION, f"correction {i}",
                       T0 + timedelta(hours=1, minutes=i), sid))
    return evs


def test_k_plafonne_lecons_compteurs_complets():
    out = lessons_learned(_many_lessons(30))            # defaut k=20
    assert len(out["lessons"]) == 20                    # sortie BORNEE par defaut
    assert out["counts"]["lessons"] == 30               # compteur COMPLET (rien de cache)
    assert out["truncated"] is True                     # la coupe est signalee
    assert out["lessons"][0]["correction"] == "correction 29"   # la plus recente d'abord


def test_standing_k_plafonne_les_verites_debout():
    evs = [_ev(EventType.DECISION, f"d{i}", T0 + timedelta(minutes=i), f"st{i}")
           for i in range(25)]
    out = lessons_learned(evs, standing_k=10)
    assert len(out["still_standing"]) == 10
    assert out["counts"]["still_standing"] == 25 and out["truncated"] is True
    assert out["still_standing"][0]["text"] == "d24"    # la plus recente d'abord


def test_superseded_k_borne_les_preuves_par_lecon():
    sid = "grosse-session"
    evs = [_ev(EventType.NOTE, f"fait {i}", T0 + timedelta(minutes=i), sid) for i in range(12)]
    evs.append(_ev(EventType.CORRECTION, "verite courante", T0 + timedelta(hours=1), sid))
    out = lessons_learned(evs)                          # defaut superseded_k=5
    lesson = out["lessons"][0]
    assert lesson["superseded_count"] == 12             # total garde (rien de cache)
    assert len(lesson["superseded"]) == 5
    assert lesson["superseded"][0]["text"] == "fait 11"  # les plus proches de la correction


def test_plafonds_none_rendent_tout():
    out = lessons_learned(_many_lessons(30), k=None, standing_k=None, superseded_k=None)
    assert len(out["lessons"]) == 30 and out["truncated"] is False


def test_filtre_source_isole_le_projet():
    evs = [
        _ev(EventType.DECISION, "ici", T0, "sa", src="project:MultiService-IA"),
        _ev(EventType.DECISION, "ailleurs", T0, "sb", src="project:AetherCore"),
    ]
    out = lessons_learned(evs, source_prefix="project:MultiService-IA")
    assert out["counts"]["still_standing"] == 1
    assert out["still_standing"][0]["text"] == "ici"
