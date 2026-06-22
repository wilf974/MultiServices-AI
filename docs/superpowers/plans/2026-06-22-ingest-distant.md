# Ingest distant authentifié — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permettre à un poste distant autorisé d'**écrire** un événement dans le journal central, via `POST /ingest` en **mTLS + HMAC + anti-rejeu**, sans toucher la surface MCP (lecture seule).

**Architecture:** Un conteneur d'ingest **séparé** (Starlette, journal monté **RW**) derrière nginx (`location /ingest`, mTLS). La logique de validation est **pure** et testable ; elle réutilise `projlog.make_event` pour produire des événements identiques à la capture locale. Le conteneur de lecture reste **`:ro`**.

**Tech Stack:** Python 3.13, Starlette + uvicorn, httpx (client), HMAC-SHA256, openssl (CA/certs), Docker, nginx, pytest.

## Global Constraints

- **Python >= 3.11** (cible 3.13). `requires-python` inchangé.
- **D5** : l'écriture passe **hors MCP** (endpoint séparé, jamais un outil MCP).
- **Append-only** : l'ingest n'écrit que de **nouveaux** événements (id uuid4), jamais de réécriture.
- **Provenance C2 imposée** : `source = registre[CN].source` ; toute `source` du payload est ignorée.
- **mTLS + HMAC + anti-rejeu** : cert client (CA dédiée) ; HMAC-SHA256 du corps brut ; `ts` dans **±300 s** ; `nonce` unique (store persistant).
- **Isolation** : conteneur ingest = journal **RW** sur port **8303** ; conteneur lecture reste **`:ro`** (port 8302). Le **registre** (clés HMAC) vit **hors** de `~/.aethercore` (jamais lisible par le conteneur de lecture).
- **Jamais de secret journalisé** (clés HMAC, clés privées de cert).
- **Sorties console en ASCII**. Chaque tâche laisse un **test de régression**.

---

### Task 1 : Logique d'ingest (pure) + tests

**Files:**
- Create: `multiservice/ingest.py`
- Test: `tests/test_ingest.py`

**Interfaces:**
- Consumes: `multiservice.projlog.make_event(kind, text, source, session_id, now) -> AetherEvent`, `multiservice.projlog.KINDS` (dict), `multiservice.journal.append_events(path, events)`, `multiservice.journal.read_events(path)`.
- Produces:
  - `verify_hmac(body: bytes, signature: str, key: str) -> bool`
  - `check_freshness(ts: str, now: datetime, window_s: int = 300) -> bool`
  - `NonceStore(path)` avec `seen(nonce)->bool`, `add(nonce, ts)`, `prune(now, window_s=300)`
  - `ingest(payload: dict, cn: str, signature: str, body: bytes, registry: dict, journal_path, nonce_store: NonceStore, now=None, window_s=300) -> dict` (`{"status": int, "id"?: str, "source"?: str, "error"?: str}`)

- [ ] **Step 1 : Écrire les tests qui échouent — `tests/test_ingest.py`**

```python
"""Regression ingest distant : auth (HMAC/CN), anti-rejeu (ts/nonce), provenance forcee, validation."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone, timedelta

from multiservice import ingest as ing
from multiservice.journal import read_events

KEY = "deadbeefcafe"
REG = {"bureau": {"source": "project:bureau", "hmac_key": KEY}}
NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def _sign(body: bytes, key: str = KEY) -> str:
    return hmac.new(key.encode(), body, hashlib.sha256).hexdigest()


def _payload(**kw):
    p = {"text": "une decision", "kind": "decision", "session": "s",
         "ts": NOW.isoformat(), "nonce": "n1"}
    p.update(kw)
    return p


def test_verify_hmac_ok_and_ko():
    b = b'{"x":1}'
    assert ing.verify_hmac(b, _sign(b), KEY) is True
    assert ing.verify_hmac(b, "bad", KEY) is False
    assert ing.verify_hmac(b, _sign(b), "wrongkey") is False


def test_check_freshness_window():
    assert ing.check_freshness(NOW.isoformat(), NOW) is True
    assert ing.check_freshness((NOW - timedelta(seconds=600)).isoformat(), NOW) is False
    assert ing.check_freshness("pas une date", NOW) is False


def test_happy_path_appends_and_forces_source(tmp_path):
    jp = tmp_path / "j.jsonl"
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    p = _payload(source="project:HACKER")          # tentative d'usurpation
    body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)
    assert r["status"] == 201
    assert r["source"] == "project:bureau"          # source IMPOSEE par le CN, pas project:HACKER
    evs = read_events(str(jp))
    assert len(evs) == 1 and evs[0].source == "project:bureau"


def test_unknown_cn_rejected(tmp_path):
    p = _payload(); body = json.dumps(p).encode()
    r = ing.ingest(p, "inconnu", _sign(body), body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_bad_signature_rejected(tmp_path):
    p = _payload(); body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", "00" * 32, body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_stale_timestamp_rejected(tmp_path):
    p = _payload(ts=(NOW - timedelta(hours=1)).isoformat()); body = json.dumps(p).encode()
    r = ing.ingest(p, "bureau", _sign(body), body, REG, str(tmp_path / "j"),
                   ing.NonceStore(tmp_path / "n"), now=NOW)
    assert r["status"] == 401


def test_replayed_nonce_rejected(tmp_path):
    jp = tmp_path / "j"; ns = ing.NonceStore(tmp_path / "n")
    p = _payload(); body = json.dumps(p).encode()
    assert ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)["status"] == 201
    assert ing.ingest(p, "bureau", _sign(body), body, REG, str(jp), ns, now=NOW)["status"] == 409


def test_invalid_kind_and_empty_text(tmp_path):
    ns = ing.NonceStore(tmp_path / "n")
    p1 = _payload(kind="evil"); b1 = json.dumps(p1).encode()
    assert ing.ingest(p1, "bureau", _sign(b1), b1, REG, str(tmp_path / "j"), ns, now=NOW)["status"] == 422
    p2 = _payload(text="   ", nonce="n2"); b2 = json.dumps(p2).encode()
    assert ing.ingest(p2, "bureau", _sign(b2), b2, REG, str(tmp_path / "j"), ns, now=NOW)["status"] == 422


def test_nonce_store_prune(tmp_path):
    ns = ing.NonceStore(tmp_path / "n.jsonl")
    ns.add("old", (NOW - timedelta(hours=1)).isoformat())
    ns.add("fresh", NOW.isoformat())
    ns.prune(NOW, window_s=300)
    assert ns.seen("old") is False and ns.seen("fresh") is True
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: FAIL (`ModuleNotFoundError: multiservice.ingest`)

- [ ] **Step 3 : Implémenter `multiservice/ingest.py`**

```python
"""Ingest distant authentifie : valide un evenement recu et l'append au journal central.
Ecriture HORS MCP (D5). Logique pure ; seuls append / nonce-store touchent le disque.
La provenance (source) est IMPOSEE par l'identite du certificat (registre CN->source)."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from . import projlog
from .journal import append_events


def verify_hmac(body: bytes, signature: str, key: str) -> bool:
    """Compare en TEMPS CONSTANT HMAC-SHA256(body, key) a la signature hex fournie."""
    if not signature or not key:
        return False
    expected = hmac.new(key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.strip())


def check_freshness(ts: str, now: datetime, window_s: int = 300) -> bool:
    """True si l'horodatage ISO8601 est dans +-window_s de now."""
    try:
        t = datetime.fromisoformat(ts)
    except (ValueError, TypeError):
        return False
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    return abs((now - t).total_seconds()) <= window_s


class NonceStore:
    """Magasin persistant de nonces (jsonl). Anti-rejeu. IO au bord."""

    def __init__(self, path):
        self.path = Path(path)

    def _load(self) -> Dict[str, str]:
        out: Dict[str, str] = {}
        if self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    out[rec["nonce"]] = rec["ts"]
                except (json.JSONDecodeError, KeyError):
                    continue
        return out

    def seen(self, nonce: str) -> bool:
        return nonce in self._load()

    def add(self, nonce: str, ts: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({"nonce": nonce, "ts": ts}) + "\n")

    def prune(self, now: datetime, window_s: int = 300) -> None:
        kept = [{"nonce": n, "ts": t} for n, t in self._load().items()
                if check_freshness(t, now, window_s)]
        tmp = self.path.with_suffix(".tmp")
        tmp.parent.mkdir(parents=True, exist_ok=True)
        tmp.write_text("".join(json.dumps(r) + "\n" for r in kept), encoding="utf-8")
        tmp.replace(self.path)


def ingest(payload: Dict[str, Any], cn: str, signature: str, body: bytes,
           registry: Dict[str, Dict[str, str]], journal_path, nonce_store: NonceStore,
           now: Optional[datetime] = None, window_s: int = 300) -> Dict[str, Any]:
    """Valide puis append. Retourne {status, id?/source?/error?}. PUR (IO au bord)."""
    now = now or datetime.now(timezone.utc)
    client = registry.get(cn)
    if client is None:
        return {"status": 401, "error": "unknown client"}
    if not verify_hmac(body, signature, client.get("hmac_key", "")):
        return {"status": 401, "error": "bad signature"}
    if not check_freshness(payload.get("ts", ""), now, window_s):
        return {"status": 401, "error": "stale timestamp"}
    nonce = payload.get("nonce", "")
    if not nonce or nonce_store.seen(nonce):
        return {"status": 409, "error": "replay"}
    kind = payload.get("kind", "")
    text = payload.get("text", "")
    if kind not in projlog.KINDS:
        return {"status": 422, "error": "invalid kind"}
    if not text or not text.strip():
        return {"status": 422, "error": "empty text"}
    source = client["source"]                       # C2 IMPOSEE (on ignore payload.source)
    session = payload.get("session") or "ingest"
    try:
        ev = projlog.make_event(kind, text, source=source, session_id=session, now=now)
    except ValueError as e:
        return {"status": 422, "error": str(e)}
    if isinstance(payload.get("data"), dict):
        ev.data.update(payload["data"])
    append_events(journal_path, [ev])
    nonce_store.add(nonce, payload["ts"])
    return {"status": 201, "id": ev.id, "source": source}
```

- [ ] **Step 4 : Vérifier le succès**

Run: `python -m pytest tests/test_ingest.py -q`
Expected: tous PASS

- [ ] **Step 5 : Commit**

```bash
git add multiservice/ingest.py tests/test_ingest.py
git commit -m "feat(ingest): logique pure d'ingest distant (HMAC, anti-rejeu, source forcee) + tests"
```

---

### Task 2 : Serveur HTTP d'ingest (Starlette) + points d'entrée

**Files:**
- Create: `multiservice/ingest_server.py`
- Modify: `pyproject.toml` (sections `[project.optional-dependencies]` et `[project.scripts]`)
- Test: `tests/test_ingest_server.py`

**Interfaces:**
- Consumes: `multiservice.ingest.ingest`, `multiservice.ingest.NonceStore`, `multiservice.config`.
- Produces: `build_app(registry_path=None, journal_path=None, nonce_path=None) -> Starlette`, `main()`, console scripts `multiservice-ingest` et `memlog-http`.

- [ ] **Step 1 : Écrire les tests qui échouent — `tests/test_ingest_server.py`**

```python
"""Regression : la route POST /ingest mappe la logique d'ingest sur les bons codes HTTP."""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest

pytest.importorskip("starlette")
from starlette.testclient import TestClient

from multiservice.ingest_server import build_app

KEY = "deadbeefcafe"


def _client(tmp_path):
    reg = tmp_path / "reg.json"
    reg.write_text(json.dumps({"bureau": {"source": "project:bureau", "hmac_key": KEY}}), encoding="utf-8")
    app = build_app(registry_path=str(reg), journal_path=str(tmp_path / "j.jsonl"),
                    nonce_path=str(tmp_path / "n.jsonl"))
    return TestClient(app)


def _post(client, body: bytes, cn="bureau", key=KEY):
    sig = hmac.new(key.encode(), body, hashlib.sha256).hexdigest()
    return client.post("/ingest", content=body,
                       headers={"X-Client-CN": cn, "X-Mem-Signature": sig,
                                "Content-Type": "application/json"})


def test_post_ingest_created(tmp_path):
    from datetime import datetime, timezone
    c = _client(tmp_path)
    body = json.dumps({"text": "ok", "kind": "note", "session": "s",
                       "ts": datetime.now(timezone.utc).isoformat(), "nonce": "z1"}).encode()
    r = _post(c, body)
    assert r.status_code == 201
    assert r.json()["source"] == "project:bureau"


def test_post_ingest_bad_json_422(tmp_path):
    c = _client(tmp_path)
    r = _post(c, b"{not json}")
    assert r.status_code == 422


def test_post_ingest_unknown_cn_401(tmp_path):
    from datetime import datetime, timezone
    c = _client(tmp_path)
    body = json.dumps({"text": "x", "kind": "note", "session": "s",
                       "ts": datetime.now(timezone.utc).isoformat(), "nonce": "z2"}).encode()
    r = _post(c, body, cn="inconnu")
    assert r.status_code == 401
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `python -m pytest tests/test_ingest_server.py -q`
Expected: FAIL (`ModuleNotFoundError: multiservice.ingest_server`)

- [ ] **Step 3 : Implémenter `multiservice/ingest_server.py`**

```python
"""Surface HTTP d'ingest (Starlette). Lit X-Client-CN (pose par nginx apres mTLS),
X-Mem-Signature et le corps brut, puis delegue a ingest.ingest(). Ecriture HORS MCP (D5)."""
from __future__ import annotations

import json
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route

from . import config, ingest as ing

_DEF_REG = str(Path(config.AETHER_HOME) / "ingest-clients.json")
_DEF_NONCE = str(Path(config.AETHER_HOME) / "ingest-nonces.jsonl")


def _registry(path: str) -> dict:
    p = Path(path)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def build_app(registry_path: str = None, journal_path: str = None, nonce_path: str = None) -> Starlette:
    registry_path = registry_path or os.environ.get("MULTISERVICE_INGEST_REGISTRY", _DEF_REG)
    journal_path = journal_path or config.JOURNAL_PATH
    nonce_path = nonce_path or os.environ.get("MULTISERVICE_INGEST_NONCES", _DEF_NONCE)

    async def ingest_route(request):
        body = await request.body()
        cn = request.headers.get("x-client-cn", "")
        sig = request.headers.get("x-mem-signature", "")
        try:
            payload = json.loads(body)
        except json.JSONDecodeError:
            return JSONResponse({"error": "invalid json"}, status_code=422)
        r = ing.ingest(payload, cn, sig, body, _registry(registry_path),
                       journal_path, ing.NonceStore(nonce_path))
        status = r.pop("status")
        return JSONResponse(r, status_code=status)

    return Starlette(routes=[Route("/ingest", ingest_route, methods=["POST"])])


def main() -> None:
    import uvicorn
    host = os.environ.get("MULTISERVICE_INGEST_HOST", "0.0.0.0")
    port = int(os.environ.get("MULTISERVICE_INGEST_PORT", "8303"))
    uvicorn.run(build_app(), host=host, port=port)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4 : Ajouter dépendances + scripts dans `pyproject.toml`**

Sous `[project.optional-dependencies]`, ajouter :
```toml
ingest = ["starlette>=0.40", "uvicorn>=0.30", "httpx>=0.27"]   # serveur + client d'ingest distant
```
Sous `[project.scripts]`, ajouter :
```toml
multiservice-ingest = "multiservice.ingest_server:main"        # serveur HTTP d'ingest (conteneur)
memlog-http = "multiservice.memlog_http:main"                  # client d'ecriture distante (Task 3)
```
Puis : `pip install -e ".[mcp,ingest]"`

- [ ] **Step 5 : Vérifier le succès**

Run: `python -m pytest tests/test_ingest_server.py -q`
Expected: 3 PASS

- [ ] **Step 6 : Commit**

```bash
git add multiservice/ingest_server.py pyproject.toml tests/test_ingest_server.py
git commit -m "feat(ingest): serveur Starlette POST /ingest + scripts (multiservice-ingest, memlog-http)"
```

---

### Task 3 : Client `memlog-http` (écriture distante)

**Files:**
- Create: `multiservice/memlog_http.py`
- Test: `tests/test_memlog_http.py`

**Interfaces:**
- Produces: `build_request(text, kind, session, hmac_key, now=None) -> tuple[bytes, str]` (corps JSON, signature hex), `main()`.

- [ ] **Step 1 : Écrire le test qui échoue — `tests/test_memlog_http.py`**

```python
"""Regression : le client construit un corps signe verifiable, avec nonce unique et ts ISO."""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import datetime, timezone

from multiservice.memlog_http import build_request

KEY = "deadbeefcafe"
NOW = datetime(2026, 6, 22, 12, 0, 0, tzinfo=timezone.utc)


def test_build_request_signed_and_wellformed():
    body, sig = build_request("ma note", "note", "sujet", KEY, now=NOW)
    payload = json.loads(body)
    assert payload["text"] == "ma note" and payload["kind"] == "note" and payload["session"] == "sujet"
    assert payload["ts"] == NOW.isoformat() and payload["nonce"]
    assert hmac.new(KEY.encode(), body, hashlib.sha256).hexdigest() == sig


def test_build_request_nonce_unique():
    b1, _ = build_request("x", "note", "s", KEY)
    b2, _ = build_request("x", "note", "s", KEY)
    assert json.loads(b1)["nonce"] != json.loads(b2)["nonce"]
```

- [ ] **Step 2 : Vérifier l'échec**

Run: `python -m pytest tests/test_memlog_http.py -q`
Expected: FAIL (`ModuleNotFoundError: multiservice.memlog_http`)

- [ ] **Step 3 : Implémenter `multiservice/memlog_http.py`**

```python
"""Client d'ecriture distante : signe et POST un evenement vers le serveur de memoire central.
Config par env : MEM_INGEST_URL, MEM_CLIENT_CERT, MEM_CLIENT_KEY, MEM_HMAC_KEY.
Le serveur impose la source via le CN du certificat ; le client ne la fixe pas."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple


def build_request(text: str, kind: str, session: str, hmac_key: str,
                  now: Optional[datetime] = None) -> Tuple[bytes, str]:
    """Construit (corps JSON, signature HMAC hex). Nonce aleatoire, ts ISO8601 UTC."""
    ts = (now or datetime.now(timezone.utc)).isoformat()
    payload = {"text": text, "kind": kind, "session": session, "ts": ts, "nonce": uuid.uuid4().hex}
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(hmac_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, sig


def main() -> None:
    p = argparse.ArgumentParser(description="Ecriture distante vers la memoire centrale (ingest mTLS).")
    p.add_argument("text")
    p.add_argument("--kind", default="decision")
    p.add_argument("--session", default="ingest")
    a = p.parse_args()

    import httpx
    url = os.environ["MEM_INGEST_URL"]
    body, sig = build_request(a.text, a.kind, a.session, os.environ["MEM_HMAC_KEY"])
    cert = (os.environ["MEM_CLIENT_CERT"], os.environ["MEM_CLIENT_KEY"])
    r = httpx.post(url, content=body, cert=cert, timeout=15,
                   headers={"X-Mem-Signature": sig, "Content-Type": "application/json"})
    print(r.status_code, r.text)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4 : Vérifier le succès + suite complète**

Run: `python -m pytest tests/test_memlog_http.py tests/test_ingest.py tests/test_ingest_server.py -q`
Expected: tous PASS

- [ ] **Step 5 : Commit**

```bash
git add multiservice/memlog_http.py tests/test_memlog_http.py
git commit -m "feat(ingest): client memlog-http (signe + POST mTLS vers /ingest)"
```

---

### Task 4 : Artefacts de déploiement (Docker + mTLS + nginx)

**Files:**
- Create: `deploy/Dockerfile.ingest`, `deploy/docker-run-ingest.sh`, `deploy/gen-mtls.sh`
- Modify: `deploy/mem.example.com.nginx` (mTLS au server + `location /ingest`)
- Modify: `deploy/README.md` (section ingest)

**Interfaces:**
- Consumes: console script `multiservice-ingest`, registre `CN->{source,hmac_key}`.
- Produces: image `mem-ingest`, conteneur sur `127.0.0.1:8303`, CA `/etc/nginx/mtls/mem/`, route `/ingest` mTLS.

- [ ] **Step 1 : `deploy/Dockerfile.ingest`**

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY multiservice ./multiservice
RUN pip install --no-cache-dir ".[ingest]"
EXPOSE 8303
ENV MULTISERVICE_INGEST_HOST=0.0.0.0 \
    MULTISERVICE_INGEST_PORT=8303
CMD ["multiservice-ingest"]
```

- [ ] **Step 2 : `deploy/docker-run-ingest.sh`** (journal RW ; registre des CLES HMAC monte depuis un dossier HORS du journal, en lecture seule)

```bash
#!/usr/bin/env bash
# Conteneur d'ingest distant : journal RW (append d'evenements), registre des cles HMAC :ro.
# Le registre vit HORS de ~/.aethercore pour ne JAMAIS etre lisible par le conteneur de lecture (:ro).
set -euo pipefail
docker rm -f mem-ingest 2>/dev/null || true
docker run -d --name mem-ingest --restart unless-stopped \
  -p 127.0.0.1:8303:8303 \
  -v /home/<user>/.aethercore:/data \
  -v /home/<user>/mem-secrets:/secrets:ro \
  -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl \
  -e MULTISERVICE_INGEST_NONCES=/data/ingest-nonces.jsonl \
  -e MULTISERVICE_INGEST_REGISTRY=/secrets/ingest-clients.json \
  -e MULTISERVICE_INGEST_HOST=0.0.0.0 -e MULTISERVICE_INGEST_PORT=8303 \
  mem-ingest
echo "mem-ingest lance sur 127.0.0.1:8303 (journal RW, registre :ro)"
```

- [ ] **Step 3 : `deploy/gen-mtls.sh`** (CA dédiée + cert client + clé HMAC + entrée registre)

```bash
#!/usr/bin/env bash
# Genere (si absent) la CA dediee mem-ingest, puis un cert CLIENT pour un CN donne + une cle HMAC.
# Usage : bash gen-mtls.sh <CN> [<source>]   ex: bash gen-mtls.sh bureau project:bureau
set -euo pipefail
CN="${1:?usage: gen-mtls.sh <CN> [source]}"
SRC="${2:-project:$CN}"
CADIR="/etc/nginx/mtls/mem"
OUT="/home/<user>/mem-secrets/clients/$CN"
mkdir -p "$CADIR" "$OUT"

if [ ! -f "$CADIR/ca.crt" ]; then
  openssl genrsa -out "$CADIR/ca.key" 4096
  openssl req -x509 -new -nodes -key "$CADIR/ca.key" -sha256 -days 3650 \
    -subj "/CN=mem-ingest-CA" -out "$CADIR/ca.crt"
  echo "CA creee : $CADIR/ca.crt"
fi

openssl genrsa -out "$OUT/client.key" 2048
openssl req -new -key "$OUT/client.key" -subj "/CN=$CN" -out "$OUT/client.csr"
openssl x509 -req -in "$OUT/client.csr" -CA "$CADIR/ca.crt" -CAkey "$CADIR/ca.key" \
  -CAcreateserial -days 825 -sha256 -out "$OUT/client.crt"
rm -f "$OUT/client.csr"

HMAC=$(openssl rand -hex 32)
echo "$HMAC" > "$OUT/hmac.key"
echo "--- Cert client + cle HMAC dans $OUT ---"
echo "Entree registre a ajouter dans /home/<user>/mem-secrets/ingest-clients.json :"
echo "  \"$CN\": { \"source\": \"$SRC\", \"hmac_key\": \"$HMAC\" }"
```

- [ ] **Step 4 : Modifier `deploy/mem.example.com.nginx`** — ajouter au bloc `server` (après les `ssl_*` existants) :

```nginx
    # mTLS pour l'ingest (CA dediee). 'optional' : /mcp reste en bearer, /ingest exige le cert.
    ssl_client_certificate /etc/nginx/mtls/mem/ca.crt;
    ssl_verify_client optional;
```
et ajouter la `location` (avant `location / { return 404; }`) :
```nginx
    location /ingest {
        if ($ssl_client_verify != SUCCESS) { return 403; }
        limit_req zone=mem burst=10 nodelay;
        proxy_pass http://127.0.0.1:8303;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Client-CN $ssl_client_s_dn_cn;   # identite imposee au service
    }
```

- [ ] **Step 5 : Ajouter une section « Ingest distant » à `deploy/README.md`**

````markdown
## Écriture distante (ingest mTLS) — phase 2

1. **CA + cert client + clé HMAC** (root) :
   ```bash
   bash /home/<user>/mem-mcp-src/deploy/gen-mtls.sh bureau project:bureau
   # ajouter l'entree imprimee dans /home/<user>/mem-secrets/ingest-clients.json
   ```
2. **Conteneur d'ingest** :
   ```bash
   cd /home/<user>/mem-mcp-src
   docker build -f deploy/Dockerfile.ingest -t mem-ingest .
   bash deploy/docker-run-ingest.sh
   ```
3. **nginx** : appliquer les ajouts mTLS + `location /ingest` du vhost, `nginx -t && systemctl reload nginx`.
4. **Poste client** : copier `client.crt`, `client.key`, `hmac.key`, puis :
   ```bash
   export MEM_INGEST_URL=https://mem.example.com/ingest
   export MEM_CLIENT_CERT=/chemin/client.crt MEM_CLIENT_KEY=/chemin/client.key
   export MEM_HMAC_KEY=$(cat /chemin/hmac.key)
   memlog-http "ma decision depuis le bureau" --kind decision --session bureau
   ```
   (le serveur impose `source=project:bureau` via le CN du certificat.)

> Le registre (`ingest-clients.json`) et les clés vivent dans `/home/<user>/mem-secrets/`,
> **hors** de `~/.aethercore` : le conteneur de lecture (`:ro`) ne peut pas les lire.
````

- [ ] **Step 6 : Vérifier en local** — l'image se construit, le conteneur sert `/ingest`, l'identité+HMAC sont enforcés (sans nginx, on simule le header `X-Client-CN`)

```bash
docker build -f deploy/Dockerfile.ingest -t mem-ingest .
mkdir -p /tmp/memsec && echo '{"bureau":{"source":"project:bureau","hmac_key":"deadbeefcafe"}}' > /tmp/memsec/ingest-clients.json
docker rm -f ing-loc 2>/dev/null || true
docker run -d --name ing-loc -p 127.0.0.1:8303:8303 \
  -v /tmp/memsec:/secrets:ro -e MULTISERVICE_INGEST_REGISTRY=/secrets/ingest-clients.json \
  -e MULTISERVICE_JOURNAL=/tmp/jl.jsonl -e MULTISERVICE_INGEST_NONCES=/tmp/nl.jsonl mem-ingest
sleep 3
TS=$(python -c "import datetime;print(datetime.datetime.now(datetime.timezone.utc).isoformat())")
BODY=$(printf '{"text":"ok","kind":"note","session":"s","ts":"%s","nonce":"loc1"}' "$TS")
SIG=$(printf '%s' "$BODY" | openssl dgst -sha256 -hmac "deadbeefcafe" -hex | sed 's/^.*= //')
echo "valide ->"; curl -s -o /dev/null -w "%{http_code}\n" -H "X-Client-CN: bureau" -H "X-Mem-Signature: $SIG" -H "Content-Type: application/json" -d "$BODY" http://127.0.0.1:8303/ingest
echo "CN inconnu ->"; curl -s -o /dev/null -w "%{http_code}\n" -H "X-Client-CN: nope" -H "X-Mem-Signature: $SIG" -H "Content-Type: application/json" -d "$BODY" http://127.0.0.1:8303/ingest
docker rm -f ing-loc
```
Expected : valide → `201` ; CN inconnu → `401`. (Si Docker indispo, livrer quand même et noter la vérif pour le contrôleur.)

- [ ] **Step 7 : Commit**

```bash
git add deploy/Dockerfile.ingest deploy/docker-run-ingest.sh deploy/gen-mtls.sh deploy/mem.example.com.nginx deploy/README.md
git commit -m "feat(deploy): conteneur d'ingest (journal RW) + CA mTLS + nginx /ingest + guide"
```

---

### Task 5 : Déploiement sur la VM (étapes root)

**Files:** aucun code — exécution de `deploy/README.md` (section ingest).

**Interfaces:**
- Consumes: image `mem-ingest`, `gen-mtls.sh`, vhost nginx modifié.
- Produces: `https://mem.example.com/ingest` opérationnel ; poste(s) capables d'écrire.

- [ ] **Step 1 : Mettre le code à jour sur la VM** (depuis Windows, en LOCAL)

```bash
cd "/c/Users/<user>/Claude/Projects/MultiService IA"
git archive --format=tar feature/ingest-distant | \
  ssh -p <SSH_PORT> <user>@<VPS_LAN> 'tar -x -C /home/<user>/mem-mcp-src'
```

- [ ] **Step 2 : CA + cert client + clé HMAC** (root)

```bash
mkdir -p /home/<user>/mem-secrets
bash /home/<user>/mem-mcp-src/deploy/gen-mtls.sh bureau project:bureau
# creer/mettre a jour /home/<user>/mem-secrets/ingest-clients.json avec l'entree imprimee
```
Expected: CA créée, `client.crt`/`client.key`/`hmac.key` sous `/home/<user>/mem-secrets/clients/bureau/`.

- [ ] **Step 3 : Conteneur d'ingest** (<user>)

```bash
ssh -p <SSH_PORT> <user>@<VPS_LAN> 'cd ~/mem-mcp-src && docker build -f deploy/Dockerfile.ingest -t mem-ingest . && bash deploy/docker-run-ingest.sh && docker ps --filter name=mem-ingest'
```
Expected: conteneur `Up` sur `127.0.0.1:8303`.

- [ ] **Step 4 : nginx** (root) — appliquer les ajouts mTLS + `/ingest`, puis `nginx -t && systemctl reload nginx`.
Expected: `test is successful`.

- [ ] **Step 5 : Smoke** (depuis un poste avec le cert)

```bash
export MEM_INGEST_URL=https://mem.example.com/ingest
export MEM_CLIENT_CERT=.../client.crt MEM_CLIENT_KEY=.../client.key MEM_HMAC_KEY=$(cat .../hmac.key)
memlog-http "smoke ingest depuis le bureau" --kind note --session ingest-smoke
```
Expected: `201`. Sans cert → `403`. Puis `recent`/`recall` via le serveur de lecture **montre** l'événement (source `project:bureau`).

- [ ] **Step 6 : Consigner** (règle projet)

```bash
cd "/c/Users/<user>/Claude/Projects/MultiService IA"
python -m multiservice.projlog "Ingest distant EN SERVICE : POST /ingest mTLS sur mem.example.com, conteneur mem-ingest (journal RW, registre :ro hors .aethercore), provenance imposee par CN. Poste bureau ecrit dans la memoire centrale." --kind decision --source project:MultiService-IA --session ingest-distant
```
Puis mettre à jour la note Obsidian + propager au central (`sync_memory_merge.ps1`). Annoncer l'écriture.

---

## Self-Review (effectué)

- **Couverture spec :** §4 contrat → T1 (codes/validation) + T2 (route) ; §5 auth/anti-rejeu/provenance → T1 ; §6 composants → T1/T2/T3 + T4 (infra) ; §7 concurrence RW/`:ro` → T4 (mounts) ; §8 erreurs → T1/T2 ; §9 sécurité (registre hors `.aethercore`, jamais de secret loggé) → T4 ; §10 déploiement → T5 ; §11 smoke → T4/T5.
- **Placeholders :** les `<CN>`/`<chemin>` sont des paramètres de déploiement (intentionnels), pas des TODO.
- **Cohérence des noms/types :** `ingest()`, `NonceStore`, `build_app`, `build_request`, port `8303`, env `MULTISERVICE_INGEST_*`, registre `CN->{source,hmac_key}` — cohérents T1→T5. `make_event`/`KINDS` réutilisés de `projlog` (vérifiés présents).
