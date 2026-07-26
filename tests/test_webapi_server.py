import json

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer tok-1"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    tokens = tmp_path / "tokens.json"
    tokens.write_text(json.dumps({"tok-1": {"source": "project:chatgpt"}}), encoding="utf-8")
    jrnl = tmp_path / "journal.jsonl"
    jrnl.write_text("", encoding="utf-8")
    monkeypatch.setenv("MULTISERVICE_WEBAPI_TOKENS", str(tokens))
    monkeypatch.setenv("MULTISERVICE_JOURNAL", str(jrnl))
    from multiservice.webapi_server import app
    return TestClient(app), jrnl


def test_health_no_auth(client):
    c, _ = client
    r = c.get("/health")
    assert r.status_code == 200 and r.json()["status"] == "ok"


def test_recall_requires_token(client):
    c, _ = client
    assert c.get("/recall", params={"q": "x"}).status_code == 401
    assert c.get("/recall", params={"q": "x"}, headers={"Authorization": "Bearer nope"}).status_code == 401


def test_remember_forces_source_from_token(client):
    c, jrnl = client
    # un champ 'source' dans le body doit etre IGNORE (securite C2)
    r = c.post("/remember",
               json={"text": "decision web", "kind": "decision", "session": "s", "source": "project:HACK"},
               headers=AUTH)
    assert r.status_code == 201
    assert r.json()["source"] == "project:chatgpt"
    lines = [l for l in jrnl.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(lines) == 1
    evt = json.loads(lines[0])
    assert evt["source"] == "project:chatgpt" and evt["valid_to"] is None


def test_remember_invalid_kind_422(client):
    c, _ = client
    assert c.post("/remember", json={"text": "x", "kind": "bogus"}, headers=AUTH).status_code == 422


def test_recall_and_recent(client):
    c, _ = client
    c.post("/remember", json={"text": "souvenir alpha", "kind": "note", "session": "s"}, headers=AUTH)
    rc = c.get("/recall", params={"q": "alpha"}, headers=AUTH)
    assert rc.status_code == 200
    assert any("alpha" in (h.get("text") or "") for h in rc.json()["results"])
    rr = c.get("/recent", params={"days": 1}, headers=AUTH)
    assert rr.status_code == 200 and "latest" in rr.json()


def test_openapi_has_absolute_server(client):
    c, _ = client
    spec = c.get("/openapi.json").json()
    assert spec.get("servers"), "openapi doit declarer servers (requis par Custom GPT Actions)"
    assert spec["servers"][0]["url"].startswith("https://")


def test_openapi_declares_bearer_security_not_header_param(client):
    c, _ = client
    spec = c.get("/openapi.json").json()
    schemes = spec.get("components", {}).get("securitySchemes", {})
    assert any(s.get("type") == "http" and s.get("scheme") == "bearer" for s in schemes.values()), \
        "openapi doit declarer un securityScheme http/bearer global"
    # plus aucun parametre 'authorization' en header dans les endpoints
    for path, methods in spec["paths"].items():
        for verb, op in methods.items():
            for p in op.get("parameters", []):
                assert not (p.get("name") == "authorization" and p.get("in") == "header"), \
                    f"{verb.upper()} {path} ne doit pas exposer 'authorization' en parametre header"


def test_health_signale_un_journal_illisible(client):
    """REGRESSION (incident 25-26/07/2026). Un type d'evenement inconnu du service deploye faisait
    lever read_events -> 500 sur /recall et /recent, pendant que /health repondait `ok` parce qu'il
    ne lisait PAS le journal. 25 h de panne totale sous feu vert. Un health-check aveugle a la panne
    du service qu'il surveille ment ; il doit constater, jamais supposer - et ne jamais lever."""
    from multiservice import projlog
    c, jrnl = client
    inconnu = json.dumps({
        "id": "00000000-0000-0000-0000-000000000001",
        "type": "type_inconnu_du_service",
        "source": "project:test",
        "valid_from": "2026-07-25T06:53:50Z",
        "text": "evenement d'un type que ce binaire ne connait pas",
    })
    # AU MILIEU, comme en production : read_events tolere une DERNIERE ligne partielle (ecriture
    # concurrente) mais leve sur une corruption au milieu - il ne la masque jamais.
    suivant = projlog.make_event("note", "un fait posterieur", source="project:test",
                                 session_id="s").model_dump_json()
    jrnl.write_text(inconnu + "\n" + suivant + "\n", encoding="utf-8")

    r = c.get("/health")

    assert r.status_code == 200, "un health-check ne doit JAMAIS lever : il rapporte la panne"
    body = r.json()
    assert body["status"] == "unavailable", f"doit constater la panne, pas repondre ok : {body}"
    assert body["degraded"] is True
    assert any("journal" in w.lower() for w in body["warnings"]), body["warnings"]


def test_health_reste_ok_quand_le_journal_est_lisible(client):
    c, _ = client
    c.post("/remember", json={"text": "un fait lisible", "kind": "note"}, headers=AUTH)

    body = c.get("/health").json()

    assert body["status"] == "ok" and body["degraded"] is False, body
    assert body["warnings"] == [] and body["event_count"] == 1


def test_main_refuses_without_enable(monkeypatch):
    monkeypatch.delenv("MULTISERVICE_WEBAPI_ENABLE", raising=False)
    from multiservice.webapi_server import main
    with pytest.raises(SystemExit):
        main()
