"""Page de DEV locale pour tester Ollama + memoire agentique dans le navigateur.

⛔ LOCAL ONLY : bind 127.0.0.1 par defaut (c'est ta memoire souveraine, jamais exposee).
Montre par tour : la reponse du modele, les APPELS D'OUTILS qu'il a faits (recall/remember + args +
resultat) et la provenance de routage. Toggles : memory-tools / recall-injection / cloud.
Souverainete cloud+tools respectee (un tour cloud => zero outil memoire).

Lancer :  python -m multiservice.webchat       # puis http://127.0.0.1:8765
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Dict, List, Optional
from urllib.request import urlopen

from . import config
from .chat import build_recall_context, inject_context, record_turn, serve_turn
from .events import EventType
from .journal import read_events
from .routing import Router

_SESSIONS: Dict[str, List[dict]] = {}    # historique de conversation par session (process-local)


def _tool_calls_from(agent) -> List[dict]:
    """Aplati les TOOL_CALL/TOOL_RESULT (par paires) en {tool, arguments, ok, result_preview}."""
    out: List[dict] = []
    pending = None
    for e in (getattr(agent, "tool_events", []) or []):
        if e.type == EventType.TOOL_CALL:
            pending = e
        elif e.type == EventType.TOOL_RESULT and pending is not None:
            out.append({"tool": pending.data.get("tool"),
                        "arguments": pending.data.get("arguments"),
                        "ok": e.data.get("ok"),
                        "result_preview": e.data.get("result_preview")})
            pending = None
    return out


def chat_response(router: Router, message: str, history: Optional[List[dict]] = None, *,
                  memory_tools: bool = True, recall_inject: bool = False, cloud_ok: bool = False,
                  journal_path: str = None, session_id: str = "web",
                  embedder=None, store=None) -> dict:
    """Sert un tour pour la page de dev -> dict JSON (reponse + activite memoire + provenance).
    Capture le tour (prompt/completion/token, provenance). Souverainete cloud+tools via serve_turn."""
    history = history or []
    sent = list(history) + [{"role": "user", "content": message}]
    injected = False
    # Toggle "recall" = injection RAG par l'hote (ancien mode), seulement hors memory-tools.
    if recall_inject and not memory_tools and embedder is not None and store is not None:
        ctx = build_recall_context(read_events(str(journal_path)), message, session_id,
                                   embedder=embedder, store=store)
        if ctx:
            sent = inject_context(sent, ctx)
            injected = True
    tr = serve_turn(router, message, sent, cloud_ok=cloud_ok, memory_tools=memory_tools,
                    journal_path=str(journal_path), session_id=session_id,
                    embedder=embedder, store=store)
    answer = (getattr(tr.completion, "text", "") or "") if tr.completion else ""
    if tr.completion is not None:                       # capture du tour (prompt/completion/token)
        record_turn(message, tr.completion, tr.count_source, str(journal_path), session_id,
                    routing=tr.routing)
    return {
        "answer": answer,
        "session_id": session_id,
        "model": getattr(tr.completion, "model_id", None),
        "routed_to": tr.routing.get("routed_to"),
        "routing_reason": tr.routing.get("routing_reason"),
        "used_memory_tools": tr.used_memory_tools,
        "recall_injected": injected,
        "tool_calls": _tool_calls_from(tr.agent),
    }


# --------------------------------------------------------------------------------------------------
# Serveur HTTP (stdlib, zero dependance), bind 127.0.0.1.
# --------------------------------------------------------------------------------------------------

_GGUF_CACHE: Dict[str, object] = {}      # slot unique {"path","backend"} : un GGUF charge a la fois


def _is_gguf(model: str) -> bool:
    return bool(model) and model.lower().endswith(".gguf")


def _get_gguf_backend(path: str):
    """Charge un GGUF in-process (EmbeddedGGUF), CACHE slot-unique : charger coute RAM/VRAM, on garde
    le dernier et on libere l'ancien si on change de modele."""
    if _GGUF_CACHE.get("path") == path and _GGUF_CACHE.get("backend") is not None:
        return _GGUF_CACHE["backend"]
    _GGUF_CACHE.clear()                                 # libere l'ancien modele (RAM/VRAM)
    from .backends import EmbeddedGGUF
    be = EmbeddedGGUF(model_path=path, n_ctx=config.N_CTX, n_gpu_layers=config.N_GPU_LAYERS)
    _GGUF_CACHE["path"] = path
    _GGUF_CACHE["backend"] = be
    return be


def _gguf_files() -> List[str]:
    """Liste les .gguf connus (dossier du modele configure + Claude/Projects) pour le selecteur."""
    dirs = {str(Path(config.MODEL_PATH).parent), str(Path.home() / "Claude" / "Projects")}
    found: List[str] = []
    for d in dirs:
        try:
            found += sorted(glob.glob(os.path.join(d, "*.gguf")))
        except Exception:
            pass
    return found


def _ollama_models() -> List[str]:
    """Liste les modeles installes sur Ollama (pour le selecteur de la page). [] si injoignable."""
    try:
        with urlopen(config.OLLAMA_HOST.rstrip("/") + "/api/tags", timeout=5) as r:
            data = json.loads(r.read().decode("utf-8"))
        return sorted(m.get("name", "") for m in data.get("models", []) if m.get("name"))
    except Exception:
        return []


def _handle(payload: dict) -> dict:
    message = (payload.get("message") or "").strip()
    if not message:
        return {"error": "message vide"}
    session_id = payload.get("session_id") or str(uuid.uuid4())
    memory_tools = bool(payload.get("memory_tools", True))
    recall_inject = bool(payload.get("recall", False))
    cloud = bool(payload.get("cloud", False))
    model = payload.get("model") or config.OLLAMA_MODEL

    from .backends import OllamaBackend, PerplexityBackend
    if _is_gguf(model):                                 # alternative a Ollama : GGUF in-process (cache)
        try:
            local = _get_gguf_backend(model)
        except Exception as e:
            hint = (" -- 0xc000001d = llama-cpp-python (wheel) incompatible avec l'AVX de ce CPU : "
                    "reinstaller (build source / wheel CUDA) ou utiliser Ollama (cf. CLAUDE.md)."
                    if "c000001d" in str(e).lower() else "")
            return {"error": f"chargement GGUF echoue ({model}): {e}{hint}"}
    else:
        local = OllamaBackend(model=model, host=config.OLLAMA_HOST)
    cloud_be = PerplexityBackend.from_env() if cloud else None
    router = Router(local, cloud_be)

    embedder = store = None
    if memory_tools or recall_inject:
        from .semantic import EmbeddingStore, OllamaEmbedder
        embedder = OllamaEmbedder(model=config.EMBED_MODEL, host=config.OLLAMA_HOST)
        store = EmbeddingStore(config.EMBED_PATH)

    history = _SESSIONS.setdefault(session_id, [])
    resp = chat_response(router, message, history, memory_tools=memory_tools,
                         recall_inject=recall_inject, cloud_ok=cloud,
                         journal_path=config.JOURNAL_PATH, session_id=session_id,
                         embedder=embedder, store=store)
    history.append({"role": "user", "content": message})
    history.append({"role": "assistant", "content": resp["answer"]})
    return resp


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body, ctype: str = "application/json") -> None:
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        if self.path in ("/", "/index.html"):
            self._send(200, _PAGE, "text/html; charset=utf-8")
        elif self.path == "/api/models":
            self._send(200, json.dumps({"models": _ollama_models() + _gguf_files(),
                                        "default": config.OLLAMA_MODEL}, ensure_ascii=False))
        else:
            self._send(404, "not found", "text/plain; charset=utf-8")

    def do_POST(self) -> None:
        if self.path != "/api/chat":
            self._send(404, json.dumps({"error": "not found"}))
            return
        try:
            n = int(self.headers.get("Content-Length", 0))
            payload = json.loads(self.rfile.read(n) or b"{}")
            resp = _handle(payload)
        except Exception as e:  # le serveur de dev ne crashe jamais sur une requete
            self._send(500, json.dumps({"error": str(e)}, ensure_ascii=False))
            return
        self._send(200, json.dumps(resp, ensure_ascii=False))

    def log_message(self, *a) -> None:   # silencieux
        return


def main() -> None:
    p = argparse.ArgumentParser(description="Page de dev locale : Ollama + memoire agentique.")
    p.add_argument("--host", default="127.0.0.1", help="bind (defaut 127.0.0.1 - NE PAS exposer)")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    srv = ThreadingHTTPServer((args.host, args.port), _Handler)
    print(f"Page de test : http://{args.host}:{args.port}")
    print(f"Journal      : {config.JOURNAL_PATH}")
    print(f"Modele Ollama: {config.OLLAMA_MODEL} ({config.OLLAMA_HOST})   |  Ctrl+C pour arreter.")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n[arrete]")


_PAGE = """<!doctype html><html lang="fr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>MultiService IA - test Ollama + memoire</title>
<style>
 :root{--bg:#0e1116;--panel:#171b22;--line:#262c36;--fg:#e6e6e6;--mut:#8b94a3;--acc:#39b1a6;--cloud:#c98a3a;}
 *{box-sizing:border-box} body{margin:0;font:14px/1.5 system-ui,Segoe UI,Roboto,sans-serif;background:var(--bg);color:var(--fg)}
 header{padding:10px 16px;border-bottom:1px solid var(--line);display:flex;gap:14px;align-items:center;flex-wrap:wrap}
 header b{color:var(--acc)} .toggles{display:flex;gap:14px;flex-wrap:wrap;font-size:13px;color:var(--mut)}
 .toggles label{cursor:pointer} .wrap{display:flex;height:calc(100vh - 52px)}
 .chat{flex:1;display:flex;flex-direction:column;border-right:1px solid var(--line);min-width:0}
 .msgs{flex:1;overflow:auto;padding:16px;display:flex;flex-direction:column;gap:12px}
 .m{max-width:80%;padding:9px 12px;border-radius:10px;white-space:pre-wrap;word-wrap:break-word}
 .u{align-self:flex-end;background:#243042} .a{align-self:flex-start;background:var(--panel);border:1px solid var(--line)}
 .badge{display:inline-block;font-size:11px;padding:1px 7px;border-radius:8px;margin-bottom:5px}
 .b-local{background:#173f3a;color:var(--acc)} .b-cloud{background:#3a2c17;color:var(--cloud)}
 form{display:flex;gap:8px;padding:12px;border-top:1px solid var(--line)}
 input[type=text]{flex:1;padding:10px;border-radius:8px;border:1px solid var(--line);background:#0b0e13;color:var(--fg)}
 button{padding:10px 16px;border:0;border-radius:8px;background:var(--acc);color:#04201d;font-weight:600;cursor:pointer}
 button:disabled{opacity:.5;cursor:default}
 .side{width:38%;min-width:280px;max-width:520px;overflow:auto;padding:14px;background:#0b0e13}
 .side h3{margin:0 0 8px;font-size:13px;color:var(--mut);text-transform:uppercase;letter-spacing:.04em}
 .tc{border:1px solid var(--line);border-radius:8px;padding:8px 10px;margin-bottom:8px;background:var(--panel)}
 .tc .t{color:var(--acc);font-weight:600} .tc .ko{color:#d9534f} .tc pre{margin:6px 0 0;white-space:pre-wrap;color:var(--mut);font-size:12px}
 .empty{color:var(--mut);font-style:italic}
</style></head><body>
<header>
 <b>MultiService IA</b> <span style="color:var(--mut)">test Ollama + memoire</span>
 <label style="color:var(--mut);font-size:13px">modele <input id="model" list="modellist" placeholder="qwen3.6  ou  C:\\...\\model.gguf"
   style="background:#0b0e13;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:3px 6px;width:260px">
   <datalist id="modellist"></datalist></label>
 <span class="toggles">
   <label><input type="checkbox" id="t-mem" checked> memory-tools (le modele cherche/ecrit)</label>
   <label><input type="checkbox" id="t-recall"> recall-injection (RAG hote)</label>
   <label><input type="checkbox" id="t-cloud"> cloud (Perplexity)</label>
 </span>
 <span style="margin-left:auto;color:var(--mut);font-size:12px" id="sid"></span>
</header>
<div class="wrap">
 <div class="chat">
   <div class="msgs" id="msgs"></div>
   <form id="f"><input type="text" id="in" placeholder="Pose une question, ou: retiens que..." autocomplete="off" autofocus>
     <button id="send">Envoyer</button></form>
 </div>
 <div class="side"><h3>Activite memoire (appels d'outils du modele)</h3><div id="acts"><p class="empty">Aucun appel pour l'instant.</p></div></div>
</div>
<script>
const sid = crypto.randomUUID();
document.getElementById('sid').textContent = 'session ' + sid.slice(0,8);
const modelInput=document.getElementById('model');
const savedModel=localStorage.getItem('msia_model');
fetch('/api/models').then(r=>r.json()).then(d=>{
  const dl=document.getElementById('modellist');
  (d.models||[]).forEach(m=>{const o=document.createElement('option');o.value=m;dl.appendChild(o);});
  modelInput.value = savedModel || d.default || '';
}).catch(()=>{ modelInput.value = savedModel || ''; });
modelInput.addEventListener('change', e=>localStorage.setItem('msia_model', e.target.value.trim()));
const msgs = document.getElementById('msgs'), acts = document.getElementById('acts');
function add(cls, html){const d=document.createElement('div');d.className='m '+cls;d.innerHTML=html;msgs.appendChild(d);msgs.scrollTop=msgs.scrollHeight;return d;}
function esc(s){return (s||'').replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));}
function renderActs(list){
  if(!list||!list.length){acts.innerHTML='<p class="empty">Aucun appel sur ce tour.</p>';return;}
  acts.innerHTML = list.map(t=>`<div class="tc"><span class="${t.ok?'t':'ko'}">${esc(t.tool)}</span>(${esc(JSON.stringify(t.arguments))})<pre>${esc(t.result_preview)}</pre></div>`).join('');
}
const f=document.getElementById('f'), inp=document.getElementById('in'), btn=document.getElementById('send');
f.addEventListener('submit', async e=>{
  e.preventDefault(); const message=inp.value.trim(); if(!message) return;
  add('u', esc(message)); inp.value=''; btn.disabled=true;
  const wait=add('a','<span class="empty">...</span>');
  try{
    const r=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({message,session_id:sid,model:document.getElementById('model').value,
        memory_tools:document.getElementById('t-mem').checked,
        recall:document.getElementById('t-recall').checked,
        cloud:document.getElementById('t-cloud').checked})});
    const d=await r.json();
    if(d.error){wait.innerHTML='<span class="ko">erreur: '+esc(d.error)+'</span>';}
    else{
      const cloud = d.routed_to==='cloud';
      const badge=`<span class="badge ${cloud?'b-cloud':'b-local'}">${d.routed_to} · ${esc(d.routing_reason||'')}${d.model?' · '+esc(d.model):''}</span><br>`;
      wait.innerHTML = badge + esc(d.answer);
      renderActs(d.tool_calls);
    }
  }catch(err){wait.innerHTML='<span class="ko">erreur reseau: '+esc(err)+'</span>';}
  btn.disabled=false; inp.focus();
});
</script></body></html>"""


if __name__ == "__main__":
    main()
