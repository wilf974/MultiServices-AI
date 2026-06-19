"""S15 (lecture seule) - summarize : totaux, bases, proxy de re-envoi de prefixe."""
from datetime import datetime, timedelta, timezone

from multiservice.backends import StubBackend
from multiservice.inspect import summarize
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _evts():
    be = StubBackend()
    evts = []
    # session s1 : 2 tours, entree croissante 10 -> 30 (boule de neige)
    from multiservice.backends import Completion
    c1 = Completion("r1", "qwen3.6", 10, 5)
    c2 = Completion("r2", "qwen3.6", 30, 7)
    evts += events_for_turn("a", c1, "local_tokenizer", session_id="s1", now=T0)
    evts += events_for_turn("b", c2, "local_tokenizer", session_id="s1", now=T0 + timedelta(minutes=1))
    return evts


def test_totaux_et_bases():
    s = summarize(_evts())
    assert s["totals"]["turns"] == 2
    assert s["totals"]["in"] == 40 and s["totals"]["out"] == 12
    assert ("qwen3.6", "local_tokenizer") in s["by_basis"]
    assert s["by_basis"][("qwen3.6", "local_tokenizer")]["turns"] == 2


def test_proxy_re_envoi_prefixe():
    s = summarize(_evts())
    ses = s["sessions"][0]
    # somme(in)=40, plus gros tour=30 -> re-envoi proxy = 10
    assert ses["redundant_prefix"] == 10
    assert ses["inputs"] == [10, 30]


def test_lecture_seule_n_altere_pas():
    evts = _evts()
    before = [e.id for e in evts]
    summarize(evts)
    assert [e.id for e in evts] == before
