import pytest
from pydantic import ValidationError

from multiservice.webapi import resolve_token, RememberRequest

REG = {"tok-abc": {"source": "project:chatgpt"}}


def test_resolve_token_known():
    assert resolve_token("tok-abc", REG) == "project:chatgpt"


def test_resolve_token_unknown_missing_empty():
    assert resolve_token("nope", REG) is None
    assert resolve_token(None, REG) is None
    assert resolve_token("", REG) is None


def test_resolve_token_entry_without_source():
    assert resolve_token("x", {"x": {}}) is None


def test_remember_request_defaults():
    r = RememberRequest(text="hello")
    assert r.kind == "note" and r.session == "web"


def test_remember_request_rejects_empty_and_too_long():
    with pytest.raises(ValidationError):
        RememberRequest(text="")
    with pytest.raises(ValidationError):
        RememberRequest(text="x" * 8193)
