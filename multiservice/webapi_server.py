"""API REST web (FastAPI) exposant la memoire centrale aux LLM web. CENTRAL-ONLY.
Lecture (recall/recent) + ecriture (remember, source imposee par le token). Auth bearer
(securityScheme global, pas de param authorization). OpenAPI auto (/openapi.json, /docs)
avec servers absolu + modeles de reponse, pour les Custom GPT Actions."""
from __future__ import annotations

import json
import os
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel

from . import config, journal, memory, projlog, webapi

# URL publique absolue dans openapi.json (requis par les Custom GPT Actions). Surchargeable par env.
_PUBLIC_URL = os.environ.get("MULTISERVICE_WEBAPI_PUBLIC_URL", "https://api-mem.woutils.com")
app = FastAPI(title="MultiService IA - Memory Web API", version="1.0.0",
              servers=[{"url": _PUBLIC_URL}])

# Auth bearer declaree comme securityScheme global (et NON comme parametre header) : ChatGPT
# l'injecte via la config d'auth de l'Action. auto_error=False -> on renvoie notre propre 401.
bearer_scheme = HTTPBearer(auto_error=False)


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


def require_source(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> str:
    token = creds.credentials if creds else None
    source = webapi.resolve_token(token, _load_registry())
    if not source:
        raise HTTPException(status_code=401, detail="invalid or missing token")
    return source


# --- modeles de reponse (schema OpenAPI explicite avec properties, pour les Custom GPT) ---
class HealthResponse(BaseModel):
    status: str


class MemoryHit(BaseModel):
    id: str
    type: str
    source: str
    valid_from: Optional[str] = None
    session_id: Optional[str] = None
    score: Optional[float] = None
    text: Optional[str] = None
    superseded: Optional[bool] = None


class RecallResponse(BaseModel):
    results: list[MemoryHit]


class RecentResponse(BaseModel):
    since: Optional[str] = None
    days: int
    count: Optional[int] = None
    decisions: list[dict] = []
    corrections: list[dict] = []
    latest: list[dict] = []


class RememberResponse(BaseModel):
    id: str
    source: str


@app.get("/health", response_model=HealthResponse)
def health() -> dict:
    return {"status": "ok"}


@app.get("/recall", response_model=RecallResponse)
def recall(q: str = Query(..., min_length=1), k: int = Query(10, ge=1, le=50),
           source: str = Depends(require_source)) -> dict:
    events = journal.read_events(_journal_path())
    return {"results": memory.recall(events, q, k=k)}


@app.get("/recent", response_model=RecentResponse)
def recent(days: int = Query(7, ge=1, le=90),
           source: str = Depends(require_source)) -> dict:
    events = journal.read_events(_journal_path())
    return memory.recent(events, days=days)


@app.post("/remember", status_code=201, response_model=RememberResponse)
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
