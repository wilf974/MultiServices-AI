"""Sprint 13 - test de regression : integrite C2/C3 sur la capture.

Mode d'echec documente (CLAUDE.md) : le montage bac-a-sable tronque les fichiers
fraichement edites. Ce test a ete valide sur une COPIE PROPRE (hors montage).
Ne JAMAIS committer depuis le bac a sable ; committer cote Windows.
"""
from datetime import datetime, timezone

from multiservice.backends import StubBackend
from multiservice.events import CAPTURE_TYPES, EventType
from multiservice.journal import append_events, read_events
from multiservice.router import capture_turn

T0 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)


def _turn():
    return capture_turn("resume-moi le sprint 12", StubBackend(), session_id="s1", now=T0)


def test_capture_produit_les_trois_evenements():
    evs = _turn()
    types = [e.type for e in evs]
    assert types == [EventType.PROMPT, EventType.COMPLETION, EventType.TOKEN_USAGE]


def test_c2_provenance_sur_100pct():
    for e in _turn():
        assert e.source and e.source.strip(), "C2 viole : source vide"
        assert 0.0 <= e.confidence <= 1.0


def test_c3_bitemporalite_presente():
    for e in _turn():
        assert e.valid_from is not None, "C3 : valid_from doit etre pose"
        assert e.valid_to is None, "capture : rien n'est cloture au moment du tour"


def test_token_usage_porte_count_source():
    tok = [e for e in _turn() if e.type == EventType.TOKEN_USAGE][0]
    assert tok.data["count_source"] == "stub"      # D9 : base de comptage explicite
    assert tok.data["model_id"] == "stub-echo"


def test_correlation_par_turn_id():
    evs = _turn()
    ids = {e.data["turn_id"] for e in evs}
    assert len(ids) == 1, "tous les evts d'un tour partagent un turn_id"


def test_perimetre_capture_seule():
    """Aucun type hors CAPTURE_TYPES : pas d'alerte, pas de skill_candidate, etc."""
    for e in _turn():
        assert e.type in CAPTURE_TYPES


def test_round_trip_journal_append_only(tmp_path):
    jpath = tmp_path / "journal.jsonl"
    evs = _turn()
    append_events(jpath, evs)
    append_events(jpath, _turn())          # deuxieme tour : on AJOUTE
    back = read_events(jpath)
    assert len(back) == 6                   # 3 + 3, rien ecrase
    assert [e.type for e in back[:3]] == [EventType.PROMPT, EventType.COMPLETION, EventType.TOKEN_USAGE]


def test_capture_ne_mute_pas_l_entree():
    """purete : capturer deux fois le meme prompt ne partage aucun etat."""
    a = capture_turn("x", StubBackend(), now=T0)
    b = capture_turn("x", StubBackend(), now=T0)
    assert a[0].data["turn_id"] != b[0].data["turn_id"]


def test_strip_think_normalise_la_capture():
    from multiservice.router import strip_think, events_for_turn
    from multiservice.backends import Completion
    assert strip_think("avant<think>scratch</think>apres") == "avantapres"
    assert strip_think("reponse </think>") == "reponse"                 # balise orpheline
    assert strip_think("texte normal") == "texte normal"
    assert strip_think("") == ""
    # bout en bout : le completion journalise est nettoye
    evs = events_for_turn("q", Completion("ok bonjour </think>", "eve", 3, 2), "local_tokenizer")
    comp = [e for e in evs if e.type.value == "completion"][0]
    assert "</think>" not in comp.description and comp.data["text"] == "ok bonjour"
