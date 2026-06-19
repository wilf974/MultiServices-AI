"""S15 - economy : reconciliation des comptes + detecteur de redondance (fixture)."""
from datetime import datetime, timedelta, timezone

from multiservice.backends import Completion
from multiservice.economy import detect_redundancy, usage_digest
from multiservice.inspect import summarize
from multiservice.router import events_for_turn

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _evts():
    evts = []
    # session "snowball" : entree 100->3000->3000 (gros re-envoi), modele qwen
    for i, n in enumerate((100, 3000, 3000)):
        evts += events_for_turn("u", Completion("r", "qwen3.6", n, 50),
                                 "local_tokenizer", session_id="big",
                                 now=T0 + timedelta(minutes=i))
    # session courte : 1 tour, 200 in -> sous le plancher, jamais flaggee
    evts += events_for_turn("u", Completion("r", "eve", 200, 900),
                             "local_tokenizer", session_id="small", now=T0)
    return evts


def test_reconciliation_par_base():
    s = summarize(_evts())
    # somme des in par base == total in (jamais melange, mais la somme reconcilie)
    assert sum(b["in"] for b in s["by_basis"].values()) == s["totals"]["in"]
    assert sum(b["out"] for b in s["by_basis"].values()) == s["totals"]["out"]


def test_digest_redondance_globale():
    d = usage_digest(summarize(_evts()))
    # session big : in=6100, max tour=3000 -> redondant=3100 ; small=0 -> total=3100
    assert d["total_redundant"] == 3100


def test_detecteur_flagge_le_gros_pas_le_petit():
    flags = detect_redundancy(summarize(_evts()))
    ids = {f["session_id"] for f in flags}
    assert "big" in ids            # 3100/6100 = 51% >= 50%, in >= 1000
    assert "small" not in ids      # 200 < plancher 1000


def test_detecteur_report_only_structure():
    for f in detect_redundancy(summarize(_evts())):
        # le flag DECRIT, il ne propose aucune action (pas de champ 'action'/'cache')
        assert set(f) == {"session_id", "n_turns", "input", "redundant", "pct"}


def _measured_evts():
    from datetime import datetime, timedelta, timezone
    from multiservice.backends import Completion
    from multiservice.router import events_for_turn
    T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
    evts = []
    # session compactee : envoye faible mais full eleve (economie reelle), proxy l'aurait flaggee
    for i in range(4):
        evts += events_for_turn("u", Completion("r", "eve", 300, 10), "local_tokenizer",
                                session_id="comp", now=T0 + timedelta(minutes=i),
                                full_input_tokens=1500)
    return evts


def test_detecteur_ignore_les_sessions_mesurees():
    from multiservice.economy import detect_redundancy
    from multiservice.inspect import summarize
    flags = detect_redundancy(summarize(_measured_evts()))
    assert all(f["session_id"] != "comp" for f in flags)   # compactee -> jamais flaggee a tort
