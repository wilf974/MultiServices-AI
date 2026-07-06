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
from .hygiene import looks_like_placeholder
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


# ATTENTION: `registry` contient des secrets (hmac_key) -> ne jamais logger cet argument.
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
    if not nonce:
        return {"status": 422, "error": "missing nonce"}
    if nonce_store.seen(nonce):
        return {"status": 409, "error": "replay"}
    kind = payload.get("kind", "")
    text = payload.get("text", "")
    if kind not in projlog.KINDS:
        return {"status": 422, "error": "invalid kind"}
    if not text or not text.strip():
        return {"status": 422, "error": "empty text"}
    # Garde anti-gabarit (pollution observee au journal) ; contournement VOLONTAIRE = force (C1).
    if looks_like_placeholder(text) and not bool(payload.get("force")):
        return {"status": 422,
                "error": "placeholder text (gabarit non rempli ; force=true pour outrepasser)"}
    # Curation Phase 2 : closes/rejects valides si presents (listes d'ids non vides).
    # closes = cloture C3 ciblee -> exige kind=correction (sinon inerte cote lecture).
    extra = payload.get("data")
    if extra is not None and not isinstance(extra, dict):
        return {"status": 422, "error": "invalid data (objet attendu)"}
    if isinstance(extra, dict):
        for key in ("closes", "rejects"):
            if key in extra:
                val = extra[key]
                if (not isinstance(val, list) or not val
                        or not all(isinstance(x, str) and x for x in val)):
                    return {"status": 422, "error": f"invalid {key} (liste d'ids attendue)"}
        if "closes" in extra and kind != "correction":
            return {"status": 422, "error": "closes exige kind=correction (cloture C3)"}
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
    nonce_store.prune(now, window_s)
    return {"status": 201, "id": ev.id, "source": source}
