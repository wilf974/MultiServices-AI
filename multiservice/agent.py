"""Boucle agentique de memoire - le MODELE cherche/ecrit lui-meme (function calling).

modele -> tool_calls -> l'hote execute via memory_tools (read-only, ou `remember` ecriture gardee)
-> resultat renvoye au modele -> il conclut. Chaque appel est journalise (TOOL_CALL + TOOL_RESULT)
=> auditable (on sait quoi le modele a cherche/ecrit, quand, et si ca a reussi).

Garde-fous : `max_steps` borne la boucle (anti-emballement) ; un outil en erreur (ToolError) est
RENVOYE au modele (pas de crash) ; l'ecriture est confinee a `remember` (source project:ollama,
gere dans memory_tools). Le journal n'est mute QUE par l'event NOTE de `remember` + les events
TOOL_CALL/TOOL_RESULT d'audit. Pas de recall injecte ici : c'est le modele qui decide.
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, List, Optional

from .events import AetherEvent, EventType
from .journal import append_events
from .memory_tools import ToolError, build_tool_specs, run_tool


@dataclass
class AgentResult:
    completion: Any                 # derniere Completion du modele (la reponse finale)
    tool_events: list               # events TOOL_CALL/TOOL_RESULT produits (audit)
    steps: int                      # nb d'iterations effectuees


def _preview(result: Any, n: int = 500) -> str:
    try:
        s = json.dumps(result, ensure_ascii=False)
    except Exception:
        s = str(result)
    return s[:n]


def run_with_memory_tools(backend, messages: List[dict], journal_path: str, session_id: str,
                          embedder=None, store=None, max_steps: int = 5, on_token=None) -> AgentResult:
    """Fait tourner la boucle outil jusqu'a une reponse sans tool_call (ou max_steps).
    `backend` doit accepter chat(messages, on_token=, tools=) (ex: OllamaBackend)."""
    specs = build_tool_specs()
    working = list(messages)
    turn_id = str(uuid.uuid4())
    tool_events: List[AetherEvent] = []
    completion = None
    steps = 0
    for steps in range(1, max_steps + 1):
        completion = backend.chat(working, on_token=on_token, tools=specs)
        calls = getattr(completion, "tool_calls", None)
        if not calls:
            break                                       # reponse finale (le modele a conclu)
        # rejoue le tour assistant (avec ses tool_calls) pour la suite de la conversation
        working.append({"role": "assistant", "content": completion.text or "", "tool_calls": calls})
        for tc in calls:
            fn = tc.get("function") or {}
            name = fn.get("name", "")
            args = fn.get("arguments") or {}
            if isinstance(args, str):                   # certains modeles serialisent les args en JSON
                try:
                    args = json.loads(args)
                except Exception:
                    args = {}
            tool_events.append(AetherEvent(
                type=EventType.TOOL_CALL, title="tool_call", description=name,
                source=f"llm:{getattr(backend, 'model_id', '?')}",
                observed_at=datetime.now(timezone.utc),
                data={"session_id": session_id, "turn_id": turn_id, "tool": name, "arguments": args},
            ))
            try:
                result = run_tool(name, args, journal_path,
                                  embedder=embedder, store=store, session_id=session_id)
                ok = True
            except ToolError as e:                      # erreur structuree -> renvoyee au modele
                result = {"error": e.kind, "message": str(e)}
                ok = False
            tool_events.append(AetherEvent(
                type=EventType.TOOL_RESULT, title="tool_result", description=name,
                source="memory", observed_at=datetime.now(timezone.utc),
                data={"session_id": session_id, "turn_id": turn_id, "tool": name,
                      "ok": ok, "result_preview": _preview(result)},
            ))
            working.append({"role": "tool", "tool_name": name,
                            "content": json.dumps(result, ensure_ascii=False)})
    if tool_events:                                     # audit des recherches/ecritures du modele
        append_events(journal_path, tool_events)
    return AgentResult(completion=completion, tool_events=tool_events, steps=steps)
