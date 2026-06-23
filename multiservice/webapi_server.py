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
    if authorization:
        parts = authorization.split(None, 1)
        if len(parts) == 2 and parts[0].lower() == "bearer":   # scheme insensible a la casse (RFC 6750)
            token = parts[1].strip()
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
