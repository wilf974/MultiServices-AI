"""Backends d'inference - SEULE piece a effet de bord (cf. CONCEPTION sec.10).

  StubBackend    : echo deterministe (tests, S13). Zero modele.
  EmbeddedGGUF   : n'importe quel .gguf charge IN-PROCESS via llama-cpp-python.
  OllamaBackend  : HTTP vers un Ollama local (streaming, detection CPU/GPU auto).

Tous derriere la meme interface Backend (D2 : backends interchangeables). chat() accepte
un callback on_token(delta) optionnel pour l'affichage en direct. Un backend EXPOSE le
modele, il n'ecrit jamais le journal. count_source porte la BASE de comptage (D9).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


@dataclass
class Completion:
    text: str
    model_id: str
    input_tokens: int
    output_tokens: int
    cached_tokens: int = 0


class BackendError(RuntimeError):
    """Erreur structuree d'un backend (cle absente, HTTP, reseau). `kind` est stable et
    machine-lisible ; `status`/`detail` portent le contexte fournisseur quand il existe."""

    def __init__(self, kind: str, message: str = "", status: Optional[int] = None,
                 detail: Optional[str] = None) -> None:
        super().__init__(message or kind)
        self.kind = kind
        self.status = status
        self.detail = detail


Message = Dict[str, str]
OnToken = Optional[Callable[[str], None]]


@runtime_checkable
class Backend(Protocol):
    model_id: str
    count_source: str  # 'provider_usage' | 'local_tokenizer' | 'stub'
    def generate(self, composed_prompt: str) -> Completion: ...
    def chat(self, messages: List[Message], on_token: OnToken = None) -> Completion: ...


class StubBackend:
    """Echo deterministe. count_source='stub' : ni facture, ni tokenizer reel."""

    model_id = "stub-echo"
    count_source = "stub"

    def chat(self, messages: List[Message], on_token: OnToken = None) -> Completion:
        last = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "")
        text = f"[stub] {last}"
        if on_token:
            on_token(text)
        joined = " ".join(m["content"] for m in messages)
        return Completion(text, self.model_id, len(joined.split()), len(text.split()))

    def generate(self, composed_prompt: str) -> Completion:
        return self.chat([{"role": "user", "content": composed_prompt}])


class OllamaBackend:
    """Modele servi par un Ollama local (http://localhost:11434), en STREAMING.

    Le streaming evite la lecture bloquante unique (cause du timeout sur les longues
    generations) et permet l'affichage en direct. Le comptage vient du runtime ->
    count_source='local_tokenizer'. Reste local et souverain. C'est D2 qui joue.
    """

    count_source = "local_tokenizer"

    def __init__(
        self,
        model: str = "qwen3.6",
        host: str = "http://localhost:11434",
        timeout: int = 600,
        think: bool = False,
        options: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.model_id = model
        self._url = host.rstrip("/") + "/api/chat"
        self._timeout = timeout
        self._think = think  # D13 : raisonnement coupe par defaut
        self._options = options or {}

    def chat(self, messages: List[Message], on_token: OnToken = None) -> Completion:
        payload: Dict[str, Any] = {
            "model": self.model_id, "messages": messages, "stream": True,
            "think": self._think,
        }
        if self._options:
            payload["options"] = self._options
        req = Request(
            self._url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}, method="POST",
        )
        parts: List[str] = []
        model = self.model_id
        pin = pout = 0
        with urlopen(req, timeout=self._timeout) as resp:
            for raw in resp:                       # NDJSON : une ligne JSON par token/bloc
                raw = raw.strip()
                if not raw:
                    continue
                obj = json.loads(raw.decode("utf-8"))
                delta = (obj.get("message") or {}).get("content", "") or ""
                if delta:
                    parts.append(delta)
                    if on_token:
                        on_token(delta)
                if obj.get("model"):
                    model = obj["model"]
                if obj.get("done"):
                    pin = int(obj.get("prompt_eval_count", 0))
                    pout = int(obj.get("eval_count", 0))
        return Completion("".join(parts), model, pin, pout)

    def generate(self, composed_prompt: str) -> Completion:
        return self.chat([{"role": "user", "content": composed_prompt}])


class EmbeddedGGUF:
    """GGUF embarque in-process. Model-agnostic : charge n'importe quel .gguf.

    Zero reseau, zero daemon. count_source='local_tokenizer'. KV de prefixe : ne PAS
    s'y fier pour un modele SWA (Gemma 4, D6/D7). NB : un wheel pre-compile peut heurter
    l'AVX du CPU (0xc000001d) -> dans ce cas, OllamaBackend ou build source.
    """

    count_source = "local_tokenizer"

    def __init__(
        self,
        model_path: str,
        n_ctx: int = 8192,
        n_gpu_layers: int = -1,
        chat_format: str | None = None,
        verbose: bool = False,
    ) -> None:
        from llama_cpp import Llama  # import PARESSEUX (volontaire)

        self.model_path = model_path
        self.model_id = Path(model_path).stem
        self._llm = Llama(
            model_path=model_path, n_ctx=n_ctx, n_gpu_layers=n_gpu_layers,
            chat_format=chat_format, verbose=verbose,
        )

    def chat(self, messages: List[Message], on_token: OnToken = None,
             max_tokens: int = 512, temperature: float = 0.7) -> Completion:
        r = self._llm.create_chat_completion(
            messages=messages, max_tokens=max_tokens, temperature=temperature
        )
        msg = r["choices"][0]["message"]["content"] or ""
        if on_token:
            on_token(msg)
        u = r.get("usage", {}) or {}
        return Completion(
            text=msg, model_id=self.model_id,
            input_tokens=int(u.get("prompt_tokens", 0)),
            output_tokens=int(u.get("completion_tokens", 0)),
        )

    def generate(self, composed_prompt: str) -> Completion:
        return self.chat([{"role": "user", "content": composed_prompt}])


class PerplexityBackend:
    """Backend CLOUD Perplexity (Sonar), OpenAI-compatible, stdlib `urllib` (zero dependance).

    NON LOCAL : le routeur ne le choisit que pour un tour NON sensible ET cloud explicitement
    permis (politique 'sensible -> local seul', cf. policy.decide). count_source='provider_usage'
    (la facture du fournisseur fait foi, D9). Cle via env, JAMAIS dans le repo ; erreurs
    structurees (BackendError) ; timeout explicite. Pluggable : meme interface Backend que les
    autres, donc d'autres clouds suivront le meme patron sans toucher au routeur.
    """

    count_source = "provider_usage"

    DEFAULT_URL = "https://api.perplexity.ai/chat/completions"
    DEFAULT_MODEL = "sonar"

    def __init__(self, api_key: str = "", model: str = DEFAULT_MODEL,
                 url: str = DEFAULT_URL, timeout: int = 60) -> None:
        self.model_id = model
        self._key = api_key
        self._url = url
        self._timeout = timeout

    @classmethod
    def from_env(cls) -> "PerplexityBackend":
        """Construit depuis l'environnement : PPLX_API_KEY / PPLX_MODEL / PPLX_API_URL.
        La cle reste obligatoire a l'appel (verifiee dans chat), pas a la construction."""
        import os
        return cls(
            api_key=os.environ.get("PPLX_API_KEY", ""),
            model=os.environ.get("PPLX_MODEL", cls.DEFAULT_MODEL),
            url=os.environ.get("PPLX_API_URL", cls.DEFAULT_URL),
        )

    def chat(self, messages: List[Message], on_token: OnToken = None) -> Completion:
        if not self._key:
            raise BackendError("missing_api_key",
                               "PPLX_API_KEY requis pour activer PerplexityBackend.")
        payload: Dict[str, Any] = {"model": self.model_id, "messages": messages}
        req = Request(
            self._url, data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self._key}"}, method="POST",
        )
        try:
            with urlopen(req, timeout=self._timeout) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
        except HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            raise BackendError("http_error", f"Perplexity HTTP {e.code}",
                               status=e.code, detail=body) from e
        except URLError as e:
            raise BackendError("network_error",
                               f"Perplexity injoignable : {e.reason}") from e
        text = (obj["choices"][0]["message"].get("content") or "")
        if on_token:
            on_token(text)
        u = obj.get("usage", {}) or {}
        return Completion(
            text=text, model_id=obj.get("model", self.model_id),
            input_tokens=int(u.get("prompt_tokens", 0)),
            output_tokens=int(u.get("completion_tokens", 0)),
        )

    def generate(self, composed_prompt: str) -> Completion:
        return self.chat([{"role": "user", "content": composed_prompt}])
