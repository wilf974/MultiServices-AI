"""Interface CLI de chat, cablee sur la CAPTURE (S13).

Chaque tour est journalise (prompt / completion / token_usage). CAPTURE SEULE : aucun
recall depuis le journal, aucun cache. Streaming + REPL resilient : une erreur backend
(timeout, reseau) n'interrompt JAMAIS la session et ne journalise pas de tour casse.

Usage : python -m multiservice.chat --ollama
        python -m multiservice.chat --ollama --timeout 900
        python -m multiservice.chat --stub
Commandes : /quit  /reset  /journal
"""
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional

from . import config
from .backends import Backend, Completion, OllamaBackend, StubBackend
from .cache import ResultCache
from .compose import compose
from .events import AetherEvent, EventType
from .journal import append_events, read_events
from .memory import recall, recall_semantic
from .policy import is_sensitive
from .router import events_for_turn
from .semcache import SemanticCache

Message = Dict[str, str]


def build_recall_context(events, query, session_id, k=3,
                         min_score=0.4, max_chars=300, embedder=None, store=None):
    """Bloc de CONTEXTE a injecter : souvenirs pertinents du journal. PUR, LECTURE SEULE.
    - HYBRIDE si embedder+store fournis (recall_semantic, repli lexical auto) ; sinon lexical ;
    - exclut la session COURANTE (deja dans le fil vivant, pas de doublon) ;
    - filtre le SENSIBLE (on n'injecte jamais de contenu sensible dans le prompt) ;
    - garde le top-k au-dessus d'un plancher de pertinence, tronque chaque extrait.
    Retourne '' si rien de pertinent (pas d'injection a vide)."""
    if embedder is not None and store is not None:
        hits = recall_semantic(events, query, embedder, store, k=max(k * 3, k),
                               min_fused=min_score, sem_weight=0.7)
    else:
        hits = recall(events, query, k=max(k * 3, k))
    picked = []
    for h in hits:
        if h.get("session_id") == session_id:        # deja dans le contexte vivant
            continue
        if h.get("score", h.get("fused", 0)) < min_score:   # lexical (score) ou hybride (fused)
            continue
        txt = (h.get("text") or "").strip()
        if not txt or is_sensitive(txt):             # jamais de sensible injecte
            continue
        day = (h.get("valid_from") or "")[:10]
        picked.append(f"- ({h.get('type')}, {day}) {txt[:max_chars]}")
        if len(picked) >= k:
            break
    if not picked:
        return ""
    head = "[Memoire - souvenirs pertinents du journal, pour reference seulement :]"
    return "\n".join([head, *picked])


def inject_context(sent, context_block):
    """Insere le bloc de souvenirs comme message systeme. PUR (retourne une NOUVELLE liste).
    Ephemere : n'altere PAS la conversation canonique (messages), seulement ce qui part au modele."""
    if not context_block:
        return sent
    out = list(sent)
    pos = 1 if (out and out[0].get("role") == "system") else 0
    out.insert(pos, {"role": "system", "content": context_block})
    return out


def record_turn(prompt_text: str, completion: Completion, count_source: str,
                journal_path: str | Path, session_id: str,
                now: Optional[datetime] = None, served_from: Optional[str] = None,
                full_input_tokens: Optional[int] = None) -> int:
    """Journalise un tour deja produit (append-only). Retourne le nb d'evts ecrits."""
    evs = events_for_turn(prompt_text, completion, count_source,
                          session_id=session_id, now=now, served_from=served_from,
                          full_input_tokens=full_input_tokens)
    return append_events(journal_path, evs)


def maybe_serve_semantic(semcache, prompt, session_id, journal_events, threshold):
    """Sert depuis le cache SEMANTIQUE si non sensible ET hit fiable. Sinon None.
    Garde securite : un prompt SENSIBLE n'est jamais servi depuis le cache (on n'auto-sert
    jamais un contenu sensible/nuisible). Garde C3 deja dans semcache. Retourne (Completion, sim)|None."""
    if semcache is None or is_sensitive(prompt):
        return None
    return semcache.get(prompt, session_id=session_id,
                        journal_events=journal_events, threshold=threshold)


def maybe_store_semantic(semcache, prompt, completion, session_id):
    """Met en cache SEMANTIQUE un tour, SAUF si le prompt est sensible (on ne stocke pas
    de quoi auto-servir plus tard un contenu sensible)."""
    if semcache is not None and not is_sensitive(prompt):
        semcache.put(prompt, completion, session_id=session_id)


def make_correction(text: str, session_id: str,
                    now: Optional[datetime] = None) -> AetherEvent:
    """Construit un evenement CORRECTION (C2 provenance, C3 : clOture, jamais suppression). PUR.
    L'humain marque une revision ; les souvenirs ANTERIEURS de la session deviennent `superseded`."""
    ts = now or datetime.now(timezone.utc)
    return AetherEvent(
        type=EventType.CORRECTION, title="correction", description=text,
        source="user:local", observed_at=ts,
        data={"text": text, "session_id": session_id, "turn_id": str(uuid.uuid4())},
    )


def make_note(text: str, session_id: str,
              now: Optional[datetime] = None) -> AetherEvent:
    """Note PROPOSEE par l'agent, journalisee SOUS validation humaine (C1) via /note. PUR, C2/C3.
    Provenance `agent:claude` : le contenu vient de l'agent, l'humain valide en lancant la commande.
    Permet a la memoire de COMPOUNDER a partir du raisonnement de l'agent (le MCP reste lecture seule)."""
    ts = now or datetime.now(timezone.utc)
    return AetherEvent(
        type=EventType.NOTE, title="note", description=text,
        source="agent:claude", observed_at=ts,
        data={"text": text, "session_id": session_id, "turn_id": str(uuid.uuid4())},
    )


def run_repl(backend: Backend, journal_path: str | Path, system_prompt: str = "",
             cache: Optional[ResultCache] = None, compact: bool = False,
             keep_turns: int = 6, semcache: Optional[SemanticCache] = None,
             semcache_threshold: float = 0.95, recall_ctx: bool = False,
             recall_k: int = 3, recall_min_score: float = 0.4,
             recall_embedder=None, recall_store=None) -> None:
    session_id = str(uuid.uuid4())
    messages: List[Message] = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    print(f"MultiService AI - chat ({backend.model_id}). /quit pour sortir.")
    print(f"Journal : {journal_path}\n")
    while True:
        try:
            user = input("> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not user:
            continue
        if user in {"/quit", "/exit"}:
            break
        if user == "/reset":
            messages = [{"role": "system", "content": system_prompt}] if system_prompt else []
            session_id = str(uuid.uuid4())
            print("[session reinitialisee]\n")
            continue
        if user == "/journal":
            print(f"[journal] {journal_path}\n")
            continue
        if user.startswith("/correct"):
            note = user[len("/correct"):].strip()
            if not note:
                print("[usage] /correct <ce qui etait faux ou la bonne version>\n")
                continue
            append_events(journal_path, [make_correction(note, session_id)])
            print("[correction journalisee] les souvenirs anterieurs de cette session "
                  "sont marques revises (C3).\n")
            continue
        if user.startswith("/note"):
            note = user[len("/note"):].strip()
            if not note:
                print("[usage] /note <fait/synthese a memoriser (propose par l'agent, valide par toi)>\n")
                continue
            append_events(journal_path, [make_note(note, session_id)])
            print("[note journalisee] source=agent:claude, validee par toi -> recallable.\n")
            continue

        messages.append({"role": "user", "content": user})
        served_from = None
        full_in = None
        journal_events = read_events(journal_path)
        served = cache.get(messages, session_id, journal_events) if cache else None
        sem = None if served is not None else maybe_serve_semantic(
            semcache, user, session_id, journal_events, semcache_threshold)
        if served is not None:                       # HIT exact : on ne rappelle pas le modele
            print(f"[cache exact] {served.text}\n")
            completion = served
            served_from = "result-cache"
        elif sem is not None:                        # HIT semantique : quasi-paraphrase fiable
            completion, sim = sem
            print(f"[cache semantique ~{sim:.3f}] {completion.text}\n")
            served_from = "semantic-cache"
        else:
            sent = compose(messages, keep_turns) if compact else list(messages)
            if recall_ctx:                            # memoire vivante : injecte les souvenirs pertinents
                ctx = build_recall_context(journal_events, user, session_id,
                                           k=recall_k, min_score=recall_min_score,
                                           embedder=recall_embedder, store=recall_store)
                if ctx:
                    sent = inject_context(sent, ctx)
                    print("[memoire injectee]")
            try:
                completion = backend.chat(sent, on_token=lambda t: print(t, end="", flush=True))
            except KeyboardInterrupt:
                print("\n[generation interrompue] tour ignore, session intacte.\n")
                messages.pop()
                continue
            except Exception as e:  # timeout, reseau, JSON... -> on NE crashe PAS
                print(f"\n[erreur backend: {e}]\n   -> tour ignore, rien journalise. Reessaie, /reset, ou augmente --timeout.\n")
                messages.pop()
                continue
            print("\n")
            if compact and sent is not messages:        # estimer le 'full' (ratio caracteres)
                full_chars = sum(len(m.get("content", "")) for m in messages)
                sent_chars = sum(len(m.get("content", "")) for m in sent)
                full_in = (round(completion.input_tokens * full_chars / sent_chars)
                           if sent_chars else completion.input_tokens)
            if cache is not None:
                cache.put(messages, completion, session_id=session_id)
            maybe_store_semantic(semcache, user, completion, session_id)
        messages.append({"role": "assistant", "content": completion.text})
        record_turn(user, completion, backend.count_source, journal_path, session_id,
                    served_from=served_from, full_input_tokens=full_in)


def _build_backend(args: argparse.Namespace) -> Backend:
    if args.stub:
        return StubBackend()
    if args.ollama:
        return OllamaBackend(model=args.ollama_model, host=args.ollama_host,
                             timeout=args.timeout, think=args.think)
    from .backends import EmbeddedGGUF  # import paresseux : llama_cpp requis ici seulement
    return EmbeddedGGUF(model_path=args.model, n_ctx=args.n_ctx, n_gpu_layers=args.n_gpu_layers)


def main() -> None:
    p = argparse.ArgumentParser(description="Chat local, capture journalisee (S13).")
    p.add_argument("--ollama", action="store_true", help="backend Ollama (recommande)")
    p.add_argument("--ollama-model", default=config.OLLAMA_MODEL, dest="ollama_model")
    p.add_argument("--ollama-host", default=config.OLLAMA_HOST, dest="ollama_host")
    p.add_argument("--timeout", type=int, default=config.OLLAMA_TIMEOUT,
                   help="delai max d'un tour en secondes (defaut 600)")
    p.add_argument("--think", action="store_true", help="activer le raisonnement (D13 : off par defaut)")
    p.add_argument("--stub", action="store_true", help="backend echo (test, sans modele)")
    p.add_argument("--model", default=config.MODEL_PATH, help="chemin .gguf (EmbeddedGGUF)")
    p.add_argument("--n-ctx", type=int, default=config.N_CTX, dest="n_ctx")
    p.add_argument("--n-gpu-layers", type=int, default=config.N_GPU_LAYERS, dest="n_gpu_layers")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--system", default=config.SYSTEM_PROMPT)
    p.add_argument("--cache", action="store_true", default=True, dest="cache",
                   help="cache de resultat exact (ACTIF par defaut ; --no-cache pour couper)")
    p.add_argument("--no-cache", action="store_false", dest="cache")
    p.add_argument("--cache-path", default=config.CACHE_PATH, dest="cache_path")
    p.add_argument("--compact", action="store_true", default=True, dest="compact",
                   help="cloture C3 du contexte (S16, ACTIVE par defaut)")
    p.add_argument("--no-compact", action="store_false", dest="compact",
                   help="desactive la cloture C3")
    p.add_argument("--keep-turns", type=int, default=config.KEEP_TURNS, dest="keep_turns")
    p.add_argument("--semcache", action="store_true", default=True, dest="semcache",
                   help="cache semantique S18 (ACTIF par defaut ; --no-semcache pour couper)")
    p.add_argument("--no-semcache", action="store_false", dest="semcache")
    p.add_argument("--semcache-path", default=config.SEMCACHE_PATH, dest="semcache_path")
    p.add_argument("--semcache-threshold", type=float, default=0.95, dest="semcache_threshold",
                   help="seuil decisionnel du cache semantique (defaut 0.95, calibre sur le reel)")
    p.add_argument("--recall", action="store_true", dest="recall_ctx",
                   help="memoire vivante : injecte les souvenirs pertinents du journal dans le prompt")
    p.add_argument("--recall-k", type=int, default=3, dest="recall_k")
    p.add_argument("--recall-min-score", type=float, default=0.4, dest="recall_min_score")
    args = p.parse_args()
    backend = _build_backend(args)
    cache = ResultCache(args.cache_path) if args.cache else None
    semcache = None
    if args.semcache:
        from .semantic import OllamaEmbedder
        embedder = OllamaEmbedder(model=config.EMBED_MODEL, host=config.OLLAMA_HOST)
        semcache = SemanticCache(args.semcache_path, embedder)
    recall_embedder = recall_store = None
    if args.recall_ctx:                              # injection HYBRIDE : embedder + index locaux
        from .semantic import EmbeddingStore, OllamaEmbedder
        recall_embedder = OllamaEmbedder(model=config.EMBED_MODEL, host=config.OLLAMA_HOST)
        recall_store = EmbeddingStore(config.EMBED_PATH)
    run_repl(backend, args.journal, system_prompt=args.system, cache=cache,
             compact=args.compact, keep_turns=args.keep_turns,
             semcache=semcache, semcache_threshold=args.semcache_threshold,
             recall_ctx=args.recall_ctx, recall_k=args.recall_k,
             recall_min_score=args.recall_min_score,
             recall_embedder=recall_embedder, recall_store=recall_store)


if __name__ == "__main__":
    main()
