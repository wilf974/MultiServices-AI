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
