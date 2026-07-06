"""Memoire agentique - registre d'outils LECTURE SEULE expose au modele (function calling).

Le modele DECIDE quand chercher et appelle l'outil ; l'hote execute (read-only) sur le journal et
renvoie le resultat. AUCUN outil n'ecrit le journal (D5 : la 2e surface donne acces, pas mutation) :
ce module ne fait qu'appeler `memory.*` (pur, lecture seule) sur `read_events(...)`.

`build_tool_specs()` -> specs au format function-calling Ollama/OpenAI.
`run_tool(name, args, journal_path, embedder=None, store=None)` -> resultat JSON-serialisable.
Miroir des outils du serveur MCP (meme semantique), mais cote modele local.
"""
from __future__ import annotations

import uuid
from collections import Counter
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from . import memory
from .events import AetherEvent, EventType
from .hygiene import looks_like_placeholder
from .journal import append_events, read_events

# Ecriture du modele : source IMPOSEE (jamais usurpable) + kinds bornes (non-autoritaires).
OLLAMA_SOURCE = "project:ollama"
ALLOWED_WRITE_KINDS = {"observation", "note"}          # ce que le modele peut ecrire
AUTHORITATIVE_KINDS = {"decision", "validation", "correction"}  # reserve a l'humain (C1)


class ToolError(RuntimeError):
    """Erreur structuree d'execution d'outil (outil inconnu, argument manquant, kind interdit)."""

    def __init__(self, kind: str, message: str = "") -> None:
        super().__init__(message or kind)
        self.kind = kind


def _spec(name: str, description: str, properties: Dict[str, Any],
          required: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
            },
        },
    }


def build_tool_specs() -> List[Dict[str, Any]]:
    """Panel read-only expose au modele (le modele choisit quand appeler)."""
    s = "string"
    return [
        _spec("recall", "Cherche des souvenirs pertinents (lexical, lecture seule). Filtres optionnels: "
              "source (ex 'project:chatgpt') et type (decision/note/...).",
              {"query": {"type": s, "description": "termes/sujet a rechercher"},
               "k": {"type": "integer", "description": "nb max de souvenirs (defaut 10)"},
               "source": {"type": s, "description": "filtre par source/projet (prefixe, optionnel)"},
               "type": {"type": s, "description": "filtre par type d'event (optionnel)"}},
              ["query"]),
        _spec("recall_semantic", "Recall HYBRIDE (semantique local + lexical). Suggestif.",
              {"query": {"type": s, "description": "sujet a rechercher"},
               "k": {"type": "integer", "description": "nb max (defaut 10)"}},
              ["query"]),
        _spec("recent", "Quoi de neuf : decisions/corrections/derniers events sur une fenetre. "
              "Sortie bornee (limit), compteurs complets.",
              {"days": {"type": "integer", "description": "fenetre en jours (defaut 7)"},
               "source": {"type": s, "description": "filtre par source/projet (prefixe, optionnel)"},
               "limit": {"type": "integer",
                         "description": "plafond decisions/corrections (defaut 20)"}}),
        _spec("why", "Les evenements d'un tour donne (pourquoi l'agent a vu/dit ca).",
              {"turn_id": {"type": s, "description": "identifiant du tour"}}, ["turn_id"]),
        _spec("replay", "Rejoue une session (digest compact par defaut).",
              {"session_id": {"type": s, "description": "identifiant de session"},
               "digest": {"type": "boolean", "description": "True=resume compact (defaut), False=tout"}},
              ["session_id"]),
        _spec("brief", "Brief compose sur un SUJET (souvenirs + decisions + revises + sessions).",
              {"query": {"type": s, "description": "sujet"},
               "k": {"type": "integer", "description": "nb max (defaut 5)"}}, ["query"]),
        _spec("lessons", "Lecons tirees des corrections (C3) + verite courante. Sortie bornee "
              "(k/standing_k), compteurs complets.",
              {"source": {"type": s, "description": "filtre par source/projet (prefixe, optionnel)"},
               "k": {"type": "integer", "description": "plafond lecons (defaut 20)"},
               "standing_k": {"type": "integer",
                              "description": "plafond verites debout (defaut 20)"}}),
        _spec("sources", "CARTE de toute la memoire : liste TOUS les namespaces/projets (source) avec "
              "le nombre d'entrees. A appeler pour savoir QUOI existe avant de chercher. Aucun argument.", {}),
        _spec("browse", "PARCOURIR la memoire sans mot-cle : entrees filtrees par source (projet) et/ou "
              "type, les plus recentes d'abord. Pour explorer un projet entier (la ou recall, lexical, "
              "ne matche pas).",
              {"source": {"type": s, "description": "filtre source/projet (prefixe, optionnel)"},
               "type": {"type": s, "description": "filtre type (decision/note/..., optionnel)"},
               "k": {"type": "integer", "description": "nb max d'entrees (defaut 20)"}}),
        _spec("remember",
              "Memorise une OBSERVATION dans TA memoire dediee (project:ollama, append-only). "
              "Pour tes apprentissages durables, pas le bruit. Tu ne peux pas decider/valider "
              "(reserve a l'humain) ; tu observes.",
              {"text": {"type": "string", "description": "le fait/apprentissage a memoriser"},
               "kind": {"type": "string", "description": "observation (defaut) ou note",
                        "enum": ["observation", "note"]}},
              ["text"]),
    ]


def _as_int(v, default):
    try:
        return int(v)
    except (TypeError, ValueError):
        return default


def run_tool(name: str, args: Dict[str, Any], journal_path: str,
             embedder=None, store=None, session_id: Optional[str] = None) -> Any:
    """Execute un outil et renvoie un resultat JSON-serialisable. Lecture seule SAUF `remember`
    (ecriture gardee : source forcee project:ollama, append-only, kinds non-autoritaires, dedup).
    Leve ToolError('unknown_tool' | 'bad_args' | 'forbidden_kind')."""
    args = args or {}
    events = read_events(journal_path)

    if name == "recall":
        q = args.get("query")
        if not q:
            raise ToolError("bad_args", "recall: 'query' requis")
        return memory.recall(events, q, k=_as_int(args.get("k"), 10),
                             type_=(args.get("type") or None),
                             source_prefix=(args.get("source") or None))

    if name == "sources":                              # carte complete de la memoire
        c = Counter(e.source for e in events)
        return [{"source": src, "count": n} for src, n in c.most_common()]

    if name == "browse":                               # parcourir sans mot-cle (par source/type)
        src = (args.get("source") or "").strip()
        typ = (args.get("type") or "").strip()
        sel = [e for e in events
               if (not src or e.source.startswith(src)) and (not typ or e.type.value == typ)]
        sel.sort(key=lambda e: (getattr(e, "valid_from", None) or e.observed_at), reverse=True)
        out = []
        for e in sel[:_as_int(args.get("k"), 20)]:
            vf = getattr(e, "valid_from", None)
            txt = (e.data.get("text") if isinstance(e.data, dict) else None) or e.description or ""
            out.append({"id": e.id, "type": e.type.value, "source": e.source,
                        "valid_from": vf.isoformat() if vf else None, "text": txt[:300]})
        return out

    if name == "recall_semantic":
        q = args.get("query")
        if not q:
            raise ToolError("bad_args", "recall_semantic: 'query' requis")
        k = _as_int(args.get("k"), 10)
        if embedder is not None and store is not None:
            return memory.recall_semantic(events, q, embedder, store, k=k)
        return memory.recall(events, q, k=k)           # repli lexical propre (pas d'embedder)

    if name == "recent":
        return memory.recent(events, days=_as_int(args.get("days"), 7),
                             source_prefix=(args.get("source") or None),
                             limit=_as_int(args.get("limit"), 20))

    if name == "why":
        t = args.get("turn_id")
        if not t:
            raise ToolError("bad_args", "why: 'turn_id' requis")
        return memory.why(events, t)

    if name == "replay":
        sid = args.get("session_id")
        if not sid:
            raise ToolError("bad_args", "replay: 'session_id' requis")
        digest = args.get("digest", True)
        return memory.session_digest(events, sid) if digest else memory.replay_session(events, sid)

    if name == "brief":
        q = args.get("query")
        if not q:
            raise ToolError("bad_args", "brief: 'query' requis")
        return memory.topic_brief(events, q, k=_as_int(args.get("k"), 5))

    if name == "lessons":
        return memory.lessons_learned(events,
                                      source_prefix=(args.get("source") or None),
                                      k=_as_int(args.get("k"), 20),
                                      standing_k=_as_int(args.get("standing_k"), 20))

    if name == "remember":                             # SEUL outil mutateur (ecriture gardee)
        text = (args.get("text") or "").strip()
        if not text:
            raise ToolError("bad_args", "remember: 'text' requis")
        if looks_like_placeholder(text):               # anti-gabarit ; PAS de force au modele (C1)
            raise ToolError("bad_args", "remember: texte de gabarit non rempli (placeholder)")
        kind = (args.get("kind") or "observation").strip().lower()
        if kind in AUTHORITATIVE_KINDS:                # C1 : l'humain tranche, le modele observe
            raise ToolError("forbidden_kind",
                            f"kind autoritaire reserve a l'humain : {kind!r} (utilise observation/note)")
        if kind not in ALLOWED_WRITE_KINDS:
            kind = "observation"
        for e in events:                               # dedup anti-bruit (meme texte deja memorise)
            if (e.type == EventType.NOTE and e.source == OLLAMA_SOURCE
                    and (e.data.get("text") or "").strip() == text):
                return {"id": e.id, "source": OLLAMA_SOURCE, "deduped": True}
        ev = AetherEvent(
            type=EventType.NOTE, title="note", description=text,
            source=OLLAMA_SOURCE,                       # FORCEE : le modele ne choisit pas sa source
            observed_at=datetime.now(timezone.utc),
            data={"text": text, "kind": kind,
                  "session_id": session_id or "ollama", "turn_id": str(uuid.uuid4())},
        )
        append_events(journal_path, [ev])              # append-only (C3 : jamais d'ecrasement)
        return {"id": ev.id, "source": OLLAMA_SOURCE, "kind": kind}

    raise ToolError("unknown_tool", f"outil inconnu : {name!r}")
