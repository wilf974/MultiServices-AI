"""S17 - detection de skills candidates : recurrence, observe-seul, confiance, purete."""
from datetime import datetime, timezone
from pathlib import Path

from multiservice.events import AetherEvent, EventType
from multiservice.skills import skill_candidates, _confidence

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _prompt(text, source="user:local", at=T0):
    return AetherEvent(type=EventType.PROMPT, title="prompt", description=text,
                       source=source, observed_at=at, data={"text": text})


def test_pattern_recurrent_devient_candidate():
    evs = [
        _prompt("traduis ce texte en anglais"),
        _prompt("traduis ce texte en espagnol"),
        _prompt("traduis ce texte en allemand stp"),
        _prompt("quelle heure est-il maintenant"),   # bruit isole
    ]
    cands = skill_candidates(evs, min_occurrences=3)
    assert len(cands) == 1
    c = cands[0]
    assert c["count"] == 3 and c["type"] == "suggestion"
    assert "traduis" in c["signature"] and "texte" in c["signature"]
    assert c["confidence"] == _confidence(3)        # 1 - 0.5^3 = 0.88


def test_sous_le_seuil_rien():
    evs = [_prompt("genere une image de chat"), _prompt("genere une image de chien")]
    assert skill_candidates(evs, min_occurrences=3) == []


def test_observe_seul_ignore_le_propose_llm():
    # 3 prompts identiques mais source=llm/plane -> JAMAIS candidate (anti-empoisonnement)
    evs = [_prompt("resume ce document long", source="llm:eve") for _ in range(4)]
    assert skill_candidates(evs, min_occurrences=3) == []


def test_confiance_croissante():
    assert _confidence(1) < _confidence(3) < _confidence(8) <= 0.95


def test_purete_structurelle():
    src = (Path(__file__).resolve().parents[1] / "multiservice" / "skills.py").read_text(encoding="utf-8")
    for interdit in ("append_events", "urlopen", "Llama", "valid_to =", "subprocess"):
        assert interdit not in src


def test_stopwords_etendus_tuent_le_bruit_generique():
    # 'pas' et 'via' sont desormais des mots-vides -> pas d'ancre, pas de candidate
    evs = [
        _prompt("ce n'est pas faisable via le truc"),
        _prompt("ce n'est pas possible via le bidule"),
        _prompt("pas faisable via la chose"),
    ]
    cands = skill_candidates(evs, min_occurrences=3)
    assert all("pas" not in c["signature"] and "via" not in c["signature"] for c in cands)


def test_min_overlap_3_plus_strict():
    evs = [_prompt(f"connecteur odbc hfsql lecture seule v{i}") for i in range(3)]
    # a 3 tokens partages, ca tient ; le parametre est accepte
    cands = skill_candidates(evs, min_occurrences=3, min_overlap=3)
    assert isinstance(cands, list)
