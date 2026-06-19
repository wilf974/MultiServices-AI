"""S16 - mesure exacte de l'economie compaction (full vs sent), bout en bout."""
from datetime import datetime, timezone

from multiservice.backends import Completion
from multiservice.economy import usage_digest
from multiservice.inspect import summarize
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def test_events_portent_full_et_saved():
    evs = events_for_turn("u", Completion("r", "eve", 300, 50), "local_tokenizer",
                          session_id="s1", now=T0, full_input_tokens=1200)
    tok = [e for e in evs if e.type.value == "token_usage"][0]
    assert tok.data["input_tokens"] == 300          # envoye (exact)
    assert tok.data["full_input_tokens"] == 1200     # ce qu'on aurait envoye
    assert tok.data["saved_input_tokens"] == 900     # economie reelle


def test_summarize_et_digest_aggregent_l_economie():
    evs = []
    evs += events_for_turn("a", Completion("r", "eve", 300, 10), "local_tokenizer",
                           session_id="s1", now=T0, full_input_tokens=1200)
    evs += events_for_turn("b", Completion("r", "eve", 280, 10), "local_tokenizer",
                           session_id="s1", now=T0, full_input_tokens=1500)
    s = summarize(evs)
    assert s["totals"]["saved"] == 900 + 1220
    d = usage_digest(s)
    assert d["compaction_saved"] == 2120


def test_sans_compaction_saved_reste_zero():
    evs = events_for_turn("u", Completion("r", "eve", 300, 10), "local_tokenizer",
                          session_id="s1", now=T0)            # pas de full_input_tokens
    assert summarize(evs)["totals"]["saved"] == 0
