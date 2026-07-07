"""Inbox de curation — valider les propositions en UN CLIC (lève le goulot C1).

C1 fait de l'humain le maillon rare : si valider = taper des commandes `--closes`, la curation
meurt et la mémoire pourrit. Cette inbox liste les propositions déterministes (doublons exacts,
prêtes) enrichies des TEXTES, et transforme une décision (approuver/rejeter) en payload d'écriture :
- **approuver** -> clôture C3 (`data.closes`), l'original survit ;
- **rejeter** -> `data.rejects` (le signalement ne revient plus).

Coeur PUR (`pending`, `apply_decision`, `render_html`) ; le transport (ecriture vers l'ingest
central mTLS) est isolé au bord et injectable. UI web LOCALE (stdlib, bind 127.0.0.1).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

from . import curator
from .events import AetherEvent
from .journal import read_events


def _txt(e: Optional[AetherEvent]) -> str:
    if e is None:
        return "(introuvable)"
    return (e.data.get("text") or e.description or "")


def pending(events: List[AetherEvent], k: int = 50) -> List[Dict[str, Any]]:
    """Propositions de curation EN ATTENTE (doublons exacts), enrichies des textes gardé/clos.
    PURE. Réutilise `curator.curation_report` (déjà borné, garde C3, dédup)."""
    report = curator.curation_report(events, k=k)
    by_id = {e.id: e for e in events}
    out: List[Dict[str, Any]] = []
    for p in report.get("proposals", []):
        keep = by_id.get(p["keep"])
        out.append({
            "id": p["keep"],                                  # id stable de la proposition
            "action": p["action"],
            "keep_id": p["keep"],
            "close_ids": list(p["targets"]),
            "keep_text": _txt(keep),
            "close_texts": [_txt(by_id.get(t)) for t in p["targets"]],
            "rationale": p.get("rationale", ""),
            "command": p.get("command", ""),
            "command_reject": p.get("command_reject", ""),
        })
    return out


def apply_decision(proposal: Dict[str, Any], decision: str) -> Dict[str, Any]:
    """Transforme une décision humaine en payload d'écriture. PURE (n'écrit rien).
    approuver -> correction + `data.closes` (C3) ; rejeter -> note + `data.rejects`."""
    ids = list(proposal["close_ids"])
    if decision == "approve":
        return {"text": (f"Curation approuvee (inbox) : cloture de {len(ids)} doublon(s) exact(s), "
                         f"original conserve {proposal['keep_id']}"),
                "kind": "correction", "session": curator.CLOSURE_SESSION, "data": {"closes": ids}}
    if decision == "reject":
        return {"text": "Proposition de curation rejetee (inbox) : a garder / doublon volontaire",
                "kind": "note", "session": "curation-reviews", "data": {"rejects": ids}}
    raise ValueError(f"decision inconnue : {decision!r} (approve|reject)")


def render_html(proposals: List[Dict[str, Any]]) -> str:
    """Page HTML de l'inbox : chaque proposition = garder vs clore + Approuver/Rejeter. PURE."""
    import html as _h
    if not proposals:
        cards = "<p class='ok'>Rien a valider : aucune proposition en attente.</p>"
    else:
        rows = []
        for p in proposals:
            closes = "".join(f"<div class='close'>clore <code>{_h.escape(cid[:8])}</code> : "
                             f"{_h.escape(t[:120])}</div>"
                             for cid, t in zip(p["close_ids"], p["close_texts"]))
            rows.append(
                f"<div class='card' data-id='{_h.escape(p['id'])}'>"
                f"<div class='keep'>garder <code>{_h.escape(p['keep_id'][:8])}</code> : "
                f"{_h.escape(p['keep_text'][:120])}</div>{closes}"
                f"<div class='why'>{_h.escape(p['rationale'][:140])}</div>"
                f"<div class='act'><button class='ap' onclick=\"decide('{_h.escape(p['id'])}','approve')\">Approuver</button>"
                f"<button class='rj' onclick=\"decide('{_h.escape(p['id'])}','reject')\">Rejeter</button></div>"
                f"</div>")
        cards = "\n".join(rows)
    return f"""<!doctype html><html lang=fr><meta charset=utf-8>
<title>Inbox de curation</title>
<style>body{{font:15px system-ui;max-width:760px;margin:2rem auto;color:#222}}
.card{{border:1px solid #ddd;border-radius:8px;padding:12px;margin:10px 0}}
.keep{{color:#0a7a2f}}.close{{color:#a11;margin-left:8px}}.why{{color:#666;font-size:13px;margin:6px 0}}
code{{background:#f2f2f2;padding:1px 4px;border-radius:3px}}
button{{padding:6px 14px;margin-right:8px;border:0;border-radius:6px;cursor:pointer}}
.ap{{background:#0a7a2f;color:#fff}}.rj{{background:#eee}}.ok{{color:#0a7a2f}}</style>
<h1>Inbox de curation <small>({len(proposals)})</small></h1>
{cards}
<script>
async function decide(id, d){{
 const r = await fetch('/api/decide',{{method:'POST',headers:{{'Content-Type':'application/json'}},
   body:JSON.stringify({{id, decision:d}})}});
 const j = await r.json();
 const el = document.querySelector(`[data-id="${{id}}"]`);
 if(el) el.outerHTML = `<div class=card style=color:${{j.ok?'#0a7a2f':'#a11'}}>${{j.msg}}</div>`;
}}
</script></html>"""


def build_app(journal_path: str, sender: Callable[[Dict[str, Any]], Dict[str, Any]]):
    """Serveur LOCAL (stdlib). `sender(payload)->result` isole l'ecriture (ingest mTLS en prod,
    fake en test). GET / = inbox ; POST /api/decide = approuver/rejeter -> ecriture -> reponse."""
    from http.server import BaseHTTPRequestHandler

    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body, ctype="application/json"):
            data = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path in ("/", "/index.html"):
                self._send(200, render_html(pending(read_events(journal_path))), "text/html; charset=utf-8")
            else:
                self._send(404, "{}")

        def do_POST(self):
            if self.path != "/api/decide":
                return self._send(404, "{}")
            n = int(self.headers.get("Content-Length", 0))
            req = json.loads(self.rfile.read(n) or b"{}")
            props = {p["id"]: p for p in pending(read_events(journal_path))}
            prop = props.get(req.get("id"))
            if not prop:
                return self._send(404, json.dumps({"ok": False, "msg": "proposition introuvable"}))
            try:
                result = sender(apply_decision(prop, req.get("decision", "")))
                self._send(200, json.dumps({"ok": True, "msg": f"{req.get('decision')} OK", "result": result}))
            except Exception as e:                            # transport/decision -> message, jamais de crash muet
                self._send(200, json.dumps({"ok": False, "msg": str(e)[:200]}))

        def log_message(self, *a):
            pass

    return Handler


def _central_sender(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Transport prod : ecrit via l'ingest central (mTLS + HMAC), source imposee par le cert."""
    import os
    import ssl

    import httpx

    from .memlog_http import build_request
    body, sig = build_request(payload["text"], payload["kind"], payload["session"],
                              os.environ["MEM_HMAC_KEY"], data=payload.get("data") or None)
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=os.environ["MEM_CLIENT_CERT"], keyfile=os.environ["MEM_CLIENT_KEY"])
    with httpx.Client(verify=ctx, timeout=15) as client:
        r = client.post(os.environ["MEM_INGEST_URL"], content=body,
                        headers={"X-Mem-Signature": sig, "Content-Type": "application/json"})
    return {"status": r.status_code, "body": r.text}


def main() -> None:
    import argparse
    from http.server import HTTPServer

    from . import config
    p = argparse.ArgumentParser(description="Inbox de curation (UI locale, valide en un clic).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--port", type=int, default=8766)
    a = p.parse_args()
    handler = build_app(a.journal, _central_sender)
    srv = HTTPServer(("127.0.0.1", a.port), handler)          # LOCAL only, jamais expose
    print(f"[inbox] http://127.0.0.1:{a.port} (journal {a.journal})")
    srv.serve_forever()


if __name__ == "__main__":
    main()
