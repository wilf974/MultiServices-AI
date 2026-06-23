# API REST web (memoire centrale) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer la memoire centrale aux LLM web via une API REST FastAPI (lecture recall/recent + ecriture remember), auth par token bearer mappe a une source, central-only.

**Architecture:** Deux modules — `webapi.py` (logique pure : resolve_token + modeles) et `webapi_server.py` (app FastAPI : auth bearer, routes, garde central-only). Reutilise `memory.py` (lecture), `projlog.make_event` (ecriture source-forcee) et `journal` (read/append). Servi par un conteneur `mem-api` (port 8304) derriere un sous-domaine public `api-mem.example.com` (token-only, rate-limit, sans allowlist IP).

**Tech Stack:** Python 3.13, FastAPI, uvicorn, Pydantic v2, Starlette TestClient (httpx). Docker + nginx (deploiement VPS).

## Global Constraints

- **Central-only** : le serveur refuse de demarrer sans `MULTISERVICE_WEBAPI_ENABLE=1` (jamais sur l'install locale souveraine).
- **Source imposee par le token** : aucune ecriture ne peut fixer sa `source` depuis le client (C2).
- **Bi-temporalite (C3)** : evenements ecrits avec `valid_to=null`, jamais de suppression.
- **Sorties console ASCII** (regle projet).
- **TDD strict** : test rouge -> impl -> vert -> commit. Chaque tache laisse un test de regression.
- **`/recall` v1 = lexical** (`memory.recall`) ; le semantique est differe (evite la dependance Ollama dans le conteneur public).
- Paquet = `multiservice-ia`. Ports : 8302=mcp, 8303=ingest, **8304=webapi**.

---

### Task 1 : Dependances + script console (extra `[webapi]`)

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: extra `[webapi]` (fastapi, uvicorn) + console script `multiservice-webapi` -> `multiservice.webapi_server:main`.

- [ ] **Step 1 : Ajouter l'extra `[webapi]`**

Dans `pyproject.toml`, section `[project.optional-dependencies]`, ajouter sous la ligne `ingest = [...]` :

```toml
webapi = ["fastapi>=0.115", "uvicorn>=0.30"]   # API REST web (LLM web), central-only
```

- [ ] **Step 2 : Declarer le script console**

Dans `[project.scripts]`, ajouter sous `memlog-http = ...` :

```toml
multiservice-webapi = "multiservice.webapi_server:main"   # API REST web (conteneur mem-api)
```

- [ ] **Step 3 : Installer (fastapi + httpx pour TestClient)**

Run: `pip install -e ".[webapi,ingest]"`
Expected: `Successfully installed ... fastapi ... uvicorn ...` (httpx deja via ingest).

- [ ] **Step 4 : Verifier l'import**

Run: `python -c "import fastapi, uvicorn; from fastapi.testclient import TestClient; print('ok')"`
Expected: `ok`

- [ ] **Step 5 : Commit**

```bash
git add pyproject.toml
git commit -m "build(webapi): extra [webapi] (fastapi+uvicorn) + script multiservice-webapi"
```

---

### Task 2 : `webapi.py` — logique pure (resolve_token + modele)

**Files:**
- Create: `multiservice/webapi.py`
- Test: `tests/test_webapi.py`

**Interfaces:**
- Produces: `resolve_token(token: Optional[str], registry: dict) -> Optional[str]` ; `RememberRequest` (Pydantic : `text` 1..8192, `kind`="note", `session`="web").
- Consumes: rien (pur).

- [ ] **Step 1 : Ecrire le test (rouge)**

Create `tests/test_webapi.py` :

```python
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
```

- [ ] **Step 2 : Lancer -> echec**

Run: `python -m pytest tests/test_webapi.py -q`
Expected: FAIL (`ModuleNotFoundError: multiservice.webapi`).

- [ ] **Step 3 : Implementer**

Create `multiservice/webapi.py` :

```python
"""Logique pure de l'API REST web (central-only). Aucun effet de bord.
resolve_token : token bearer -> source (registre token->source). Modele de requete remember."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


def resolve_token(token: Optional[str], registry: dict) -> Optional[str]:
    """Retourne la 'source' associee au token, ou None si token absent/inconnu/sans source."""
    if not token:
        return None
    entry = registry.get(token)
    if not isinstance(entry, dict):
        return None
    return entry.get("source") or None


class RememberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8192)
    kind: str = "note"
    session: str = "web"
```

- [ ] **Step 4 : Lancer -> vert**

Run: `python -m pytest tests/test_webapi.py -q`
Expected: PASS (5 tests).

- [ ] **Step 5 : Commit**

```bash
git add multiservice/webapi.py tests/test_webapi.py
git commit -m "feat(webapi): logique pure resolve_token + modele RememberRequest"
```

---

### Task 3 : `webapi_server.py` — app FastAPI (routes + auth + garde central-only)

**Files:**
- Create: `multiservice/webapi_server.py`
- Test: `tests/test_webapi_server.py`

**Interfaces:**
- Consumes: `webapi.resolve_token`, `webapi.RememberRequest` ; `memory.recall(events, query, k=...)`, `memory.recent(events, days=...)` ; `projlog.make_event(kind, text, source=, session_id=)` ; `journal.read_events(path)`, `journal.append_events(path, events)` ; `config.JOURNAL_PATH`.
- Produces: `app` (FastAPI) ; `main()` (garde `MULTISERVICE_WEBAPI_ENABLE=1` puis uvicorn). Endpoints : `GET /health`, `GET /recall`, `GET /recent`, `POST /remember`.

- [ ] **Step 1 : Ecrire le test (rouge)**

Create `tests/test_webapi_server.py` :

```python
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
    assert r.status_code == 200 and r.json() == {"status": "ok"}


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


def test_main_refuses_without_enable(monkeypatch):
    monkeypatch.delenv("MULTISERVICE_WEBAPI_ENABLE", raising=False)
    from multiservice.webapi_server import main
    with pytest.raises(SystemExit):
        main()
```

- [ ] **Step 2 : Lancer -> echec**

Run: `python -m pytest tests/test_webapi_server.py -q`
Expected: FAIL (`ModuleNotFoundError: multiservice.webapi_server`).

- [ ] **Step 3 : Implementer**

Create `multiservice/webapi_server.py` :

```python
"""API REST web (FastAPI) exposant la memoire centrale aux LLM web. CENTRAL-ONLY.
Lecture (recall/recent) + ecriture (remember, source imposee par le token). Auth bearer.
OpenAPI auto (/openapi.json, /docs) pour les Custom GPT Actions."""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query

from . import config, journal, memory, projlog, webapi

app = FastAPI(title="MultiService IA - Memory Web API", version="1.0.0")


def _tokens_path() -> str:
    return os.environ.get("MULTISERVICE_WEBAPI_TOKENS", "")


def _journal_path() -> str:
    return os.environ.get("MULTISERVICE_JOURNAL", config.JOURNAL_PATH)


def _load_registry() -> dict:
    p = _tokens_path()
    if p and os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {}


def require_source(authorization: Optional[str] = Header(default=None)) -> str:
    token = None
    if authorization and authorization.startswith("Bearer "):
        token = authorization[len("Bearer "):].strip()
    source = webapi.resolve_token(token, _load_registry())
    if not source:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return source


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/recall")
def recall(q: str = Query(..., min_length=1), k: int = Query(10, ge=1, le=50),
           source: str = Depends(require_source)) -> dict:
    events = journal.read_events(_journal_path())
    return {"results": memory.recall(events, q, k=k)}


@app.get("/recent")
def recent(days: int = Query(7, ge=1, le=90),
           source: str = Depends(require_source)) -> dict:
    events = journal.read_events(_journal_path())
    return memory.recent(events, days=days)


@app.post("/remember", status_code=201)
def remember(req: webapi.RememberRequest,
             source: str = Depends(require_source)) -> dict:
    try:
        evt = projlog.make_event(req.kind, req.text, source=source, session_id=req.session)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    journal.append_events(_journal_path(), [evt])
    return {"id": evt.id, "source": evt.source}


def main() -> None:
    if os.environ.get("MULTISERVICE_WEBAPI_ENABLE") != "1":
        raise SystemExit("refus: API web central-only. Definir MULTISERVICE_WEBAPI_ENABLE=1 (VPS uniquement).")
    import uvicorn
    host = os.environ.get("MULTISERVICE_WEBAPI_HOST", "0.0.0.0")
    port = int(os.environ.get("MULTISERVICE_WEBAPI_PORT", "8304"))
    uvicorn.run(app, host=host, port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4 : Lancer -> vert (+ ensemble)**

Run: `python -m pytest tests/test_webapi_server.py tests/test_webapi.py -q`
Expected: PASS (12 tests).

- [ ] **Step 5 : Commit**

```bash
git add multiservice/webapi_server.py tests/test_webapi_server.py
git commit -m "feat(webapi): serveur FastAPI (recall/remember/recent), auth token, garde central-only"
```

---

### Task 4 : Artefacts de deploiement (Docker + nginx public + token)

**Files:**
- Create: `deploy/Dockerfile.webapi`, `deploy/docker-run-webapi.sh`, `deploy/gen-webapi-token.sh`, `deploy/api-mem.example.com.nginx`
- Modify: `deploy/README.md`

**Interfaces:**
- Consumes: console script `multiservice-webapi`, registre `token->source`.
- Produces: image `mem-api`, conteneur `127.0.0.1:8304`, vhost public `api-mem.example.com`.

- [ ] **Step 1 : `deploy/Dockerfile.webapi`**

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY multiservice ./multiservice
RUN pip install --no-cache-dir ".[webapi]"
EXPOSE 8304
ENV MULTISERVICE_WEBAPI_ENABLE=1 \
    MULTISERVICE_WEBAPI_HOST=0.0.0.0 \
    MULTISERVICE_WEBAPI_PORT=8304
CMD ["multiservice-webapi"]
```

- [ ] **Step 2 : `deploy/docker-run-webapi.sh`**

```bash
#!/usr/bin/env bash
# API REST web (LLM web) : journal RW, registre tokens :ro (hors ~/.aethercore). Central-only.
set -euo pipefail
docker rm -f mem-api 2>/dev/null || true
docker run -d --name mem-api --restart unless-stopped \
  -p 127.0.0.1:8304:8304 \
  -v /home/<user>/.aethercore:/data \
  -v /home/<user>/mem-secrets:/secrets:ro \
  -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl \
  -e MULTISERVICE_WEBAPI_TOKENS=/secrets/webapi-tokens.json \
  -e MULTISERVICE_WEBAPI_ENABLE=1 \
  -e MULTISERVICE_WEBAPI_HOST=0.0.0.0 -e MULTISERVICE_WEBAPI_PORT=8304 \
  mem-api
echo "mem-api lance sur 127.0.0.1:8304 (journal RW, tokens :ro)"
```

- [ ] **Step 3 : `deploy/gen-webapi-token.sh`**

```bash
#!/usr/bin/env bash
# Genere un token API web + l'entree de registre a coller dans webapi-tokens.json.
set -euo pipefail
NAME="${1:?usage: gen-webapi-token.sh <nom> [source]}"
SRC="${2:-project:$NAME}"
TOKEN=$(openssl rand -hex 32)
echo "Token pour $NAME (source=$SRC) :"
echo "  $TOKEN"
echo "Entree a ajouter dans /home/<user>/mem-secrets/webapi-tokens.json :"
echo "  \"$TOKEN\": { \"source\": \"$SRC\" }"
```

- [ ] **Step 4 : `deploy/api-mem.example.com.nginx`**

```nginx
# API REST web PUBLIQUE : pas d'allowlist IP (LLM web = IP arbitraires), auth applicative par token + rate-limit.
limit_req_zone $binary_remote_addr zone=memapi:10m rate=60r/m;

server {
    listen 8443 ssl proxy_protocol;
    server_name api-mem.example.com;

    ssl_certificate     /etc/letsencrypt/live/api-mem.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/api-mem.example.com/privkey.pem;
    include /etc/letsencrypt/options-ssl-nginx.conf;
    ssl_dhparam /etc/letsencrypt/ssl-dhparams.pem;

    real_ip_header proxy_protocol;
    set_real_ip_from 127.0.0.1;

    add_header Strict-Transport-Security "max-age=63072000" always;
    client_max_body_size 64k;

    location / {
        limit_req zone=memapi burst=20 nodelay;
        proxy_pass http://127.0.0.1:8304;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}

server {
    listen 80;
    server_name api-mem.example.com;
    return 301 https://$host$request_uri;
}
```

- [ ] **Step 5 : Section README**

Ajouter a `deploy/README.md` une section « API REST web (LLM web) » :

````markdown
## API REST web (LLM web) — central-only

1. **Token** (root) : `bash deploy/gen-webapi-token.sh chatgpt project:chatgpt`
   puis ajouter l'entree imprimee dans `/home/<user>/mem-secrets/webapi-tokens.json`.
2. **Conteneur** : `docker build -f deploy/Dockerfile.webapi -t mem-api . && bash deploy/docker-run-webapi.sh`
3. **DNS + TLS** : pointer `api-mem.example.com` vers le VPS ; `certbot` pour le cert ;
   appliquer `deploy/api-mem.example.com.nginx` ; `nginx -t && systemctl reload nginx`.
4. **Client web** : `Authorization: Bearer <token>` sur `https://api-mem.example.com`
   (`GET /recall?q=...`, `POST /remember`, `GET /recent`, schema `GET /openapi.json`).
   La source des ecritures est imposee par le token (jamais le client).
````

- [ ] **Step 6 : Verifier en local (si Docker dispo)**

```bash
chmod +x deploy/docker-run-webapi.sh deploy/gen-webapi-token.sh
docker build -f deploy/Dockerfile.webapi -t mem-api .
mkdir -p /tmp/wt && echo '{"tok-1":{"source":"project:chatgpt"}}' > /tmp/wt/webapi-tokens.json
docker rm -f mem-api-loc 2>/dev/null || true
docker run -d --name mem-api-loc -p 127.0.0.1:8304:8304 \
  -v /tmp/wt:/secrets:ro -e MULTISERVICE_WEBAPI_TOKENS=/secrets/webapi-tokens.json \
  -e MULTISERVICE_JOURNAL=/tmp/jl.jsonl -e MULTISERVICE_WEBAPI_ENABLE=1 mem-api
sleep 3
echo "health ->"; curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8304/health
echo "recall sans token (401) ->"; curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:8304/recall?q=x"
echo "remember (201) ->"; curl -s -o /dev/null -w "%{http_code}\n" -X POST -H "Authorization: Bearer tok-1" -H "Content-Type: application/json" -d '{"text":"hello web","kind":"note","session":"s"}' http://127.0.0.1:8304/remember
docker rm -f mem-api-loc
```
Expected : health=200, recall sans token=401, remember=201. (Si Docker indispo, livrer et noter la verif pour le controleur.)

- [ ] **Step 7 : Commit**

```bash
git add deploy/Dockerfile.webapi deploy/docker-run-webapi.sh deploy/gen-webapi-token.sh deploy/api-mem.example.com.nginx deploy/README.md
git commit -m "feat(deploy): conteneur mem-api (API web) + vhost public api-mem + gen-token + guide"
```

---

### Task 5 : Deploiement VPS (root) — manuel, NON auto-execute

Suivre `deploy/README.md` § « API REST web » : DNS `api-mem.example.com`, `certbot`, `gen-webapi-token.sh`, registre, `docker build`/`run`, vhost nginx, `nginx -t && systemctl reload nginx`. Verif bout-en-bout : `curl -H "Authorization: Bearer <token>" https://api-mem.example.com/health` -> 200 ; `/recall` sans token -> 401.
