"""Memory Intelligence #3 (instrumentation) — reuse_stats : mesure de la reutilisation.

Contrat : compte les tours SERVIS depuis la memoire (cache) et les tokens epargnes, a partir des
marqueurs deja journalises (served_from / cached / saved). PUR, lecture seule, MESURE (pas predit).

Valide sur COPIE PROPRE (cf. CLAUDE.md).
"""
from datetime import datetime, timezone

from multiservice.backends import Completion
from multiservice.memory import reuse_stats
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)


def _journal():
    evs = []
    # tour normal avec fenetrage : full=300, envoye=100 -> 200 epargnes par windowing
    evs += events_for_turn("q1", Completion("r1", "eve", 100, 20), "local_tokenizer",
                           now=T0, full_input_tokens=300)
    # tour SERVI depuis le cache semantique : tout l'input (200) epargne
    evs += events_for_turn("q2", Completion("r2", "eve", 200, 10, cached_tokens=200),
                           "local_tokenizer", now=T0, served_from="semantic-cache")
    return evs


def test_compte_les_tours_servis():
    s = reuse_stats(_journal())
    assert s["turns"] == 2
    assert s["served_from_memory"] == 1
    assert s["served_pct"] == 50.0
    assert s["by_source"] == {"semantic-cache": 1}


def test_tokens_epargnes():
    s = reuse_stats(_journal())
    assert s["input_tokens_saved_by_cache"] == 200       # le hit cache
    assert s["input_tokens_saved_by_windowing"] == 200   # le fenetrage


def test_journal_vide_est_zero():
    s = reuse_stats([])
    assert s["turns"] == 0 and s["served_from_memory"] == 0 and s["served_pct"] == 0.0
    assert s["by_source"] == {}
