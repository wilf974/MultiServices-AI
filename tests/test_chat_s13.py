"""S13 - interface chat : journalisation d'un tour + import paresseux du GGUF."""
import pytest
from datetime import datetime, timezone

from multiservice.backends import StubBackend
from multiservice.chat import record_turn
from multiservice.events import EventType
from multiservice.journal import read_events

T0 = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)


def test_record_turn_journalise_trois_evts(tmp_path):
    jp = tmp_path / "journal-llm.jsonl"
    be = StubBackend()
    comp = be.chat([{"role": "user", "content": "salut"}])
    n = record_turn("salut", comp, be.count_source, jp, session_id="s1", now=T0)
    assert n == 3
    back = read_events(jp)
    assert [e.type for e in back] == [EventType.PROMPT, EventType.COMPLETION, EventType.TOKEN_USAGE]
    tok = back[2]
    assert tok.data["count_source"] == "stub"          # D9
    assert back[0].data["turn_id"] == back[2].data["turn_id"]


def test_stub_chat_utilise_le_dernier_message_user():
    be = StubBackend()
    comp = be.chat([
        {"role": "system", "content": "sys"},
        {"role": "user", "content": "premier"},
        {"role": "assistant", "content": "rep"},
        {"role": "user", "content": "deuxieme"},
    ])
    assert "deuxieme" in comp.text


def test_embedded_gguf_import_paresseux():
    """Le module s'importe sans llama_cpp ; instancier EmbeddedGGUF le requiert."""
    from multiservice.backends import EmbeddedGGUF
    with pytest.raises((ImportError, ModuleNotFoundError, OSError, ValueError)):
        EmbeddedGGUF(model_path="/nexiste/pas.gguf")
