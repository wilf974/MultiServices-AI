"""Regression : la surface HTTP reutilise build_server (parite d'outils) et reste LECTURE SEULE."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")  # SDK requis pour FastMCP

from multiservice.mcp_server import build_server, build_http_server

READ_TOOLS = {
    "recall", "why", "recall_semantic", "replay", "replay_event", "forecast",
    "brief", "recent", "usage", "reasoning", "lessons", "index_status",
}


def test_http_server_exposes_exactly_the_readonly_tools(tmp_path):
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    srv = build_server(str(jp))
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert names == READ_TOOLS  # parite + aucun outil d'ecriture ajoute par megarde


def test_read_tool_never_writes_the_journal(tmp_path):
    jp = tmp_path / "sub" / "j.jsonl"   # n'existe pas
    srv = build_server(str(jp))
    asyncio.run(srv.call_tool("recent", {"days": 7}))
    assert not jp.exists()              # la lecture ne cree ni n'ecrit jamais le journal


def test_build_http_server_reads_port_from_env(monkeypatch, tmp_path):
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    monkeypatch.setenv("MULTISERVICE_HTTP_PORT", "8302")
    srv = build_http_server(journal_path=str(jp))
    assert srv.settings.port == 8302
    assert srv.settings.host == "0.0.0.0"


def test_http_server_allows_proxied_host(tmp_path):
    # Derriere le reverse proxy authentifiant, le Host public ne doit pas etre rejete (421).
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    srv = build_http_server(journal_path=str(jp))
    assert srv.settings.transport_security is not None
    assert srv.settings.transport_security.enable_dns_rebinding_protection is False
