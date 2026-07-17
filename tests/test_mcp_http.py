"""Regression : la surface HTTP reutilise build_server (parite d'outils) et reste LECTURE SEULE."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")  # SDK requis pour FastMCP

from multiservice.mcp_server import build_server, build_http_server

READ_TOOLS = {
    "recall", "why", "recall_semantic", "replay", "replay_event", "forecast",
    "brief", "recent", "usage", "reasoning", "lessons", "index_status",
    "curation",   # rapport de curation Phase 1 (02/07/2026) - lecture seule, comme le reste
    "project_review",   # vue composee de revue de projet (06/07/2026) - lecture seule
    "health",           # sante du substrat (kit LLM universel, 06/07/2026) - lecture seule
    "as_of",            # etat actif au temps valide T (scaling Phase 3, 17/07/2026) - lecture seule
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


def test_http_server_allows_configured_hosts_with_protection_on(monkeypatch, tmp_path):
    # Protection anti-DNS-rebinding GARDEE active ; le(s) Host public(s) sont autorises explicitement.
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    monkeypatch.setenv("MULTISERVICE_HTTP_ALLOWED_HOSTS", "mem.example.com, 127.0.0.1:8302")
    srv = build_http_server(journal_path=str(jp))
    ts = srv.settings.transport_security
    assert ts.enable_dns_rebinding_protection is True
    assert "mem.example.com" in ts.allowed_hosts
    assert "127.0.0.1:8302" in ts.allowed_hosts
    assert "https://mem.example.com" in ts.allowed_origins


def test_http_server_is_fail_closed_by_default(monkeypatch, tmp_path):
    # Sans la variable : on ne desactive JAMAIS la protection (pas de bind 0.0.0.0 sans garde).
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    monkeypatch.delenv("MULTISERVICE_HTTP_ALLOWED_HOSTS", raising=False)
    srv = build_http_server(journal_path=str(jp))
    ts = srv.settings.transport_security
    assert ts is None or ts.enable_dns_rebinding_protection is not False
