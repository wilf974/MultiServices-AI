"""Routeur - logique PURE : List[AetherEvent] en sortie, aucun effet de bord.

Sprint 13 = CAPTURE SEULE : pas de recall, pas de cache, pas de detecteur.
  events_for_turn(prompt, completion, count_source) -> evts d'un tour deja produit (pur).
  capture_turn(prompt, backend)                     -> appelle le backend puis ci-dessus.

L'historique de session vivant (chat) n'est PAS du recall : c'est le contexte du tour,
normal pour un modele de chat. Le recall depuis le journal viendra plus tard.
"""
from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from .backends import Backend, Completion
from .events import AetherEvent, EventType


def _now(now: Optional[datetime]) -> datetime:
    return now or datetime.now(timezone.utc)


_THINK_BLOCK = re.compile(r"<think>.*?</think>", re.DOTALL | re.IGNORECASE)
_THINK_TAG = re.compile(r"</?think>", re.IGNORECASE)


def strip_think(text: str) -> str:
    """Retire les blocs <think>...</think> et toute balise orpheline. PUR.
    Normalisation a la capture : le scratchpad du modele ne pollue pas la memoire."""
    if not text:
        return text
    text = _THINK_BLOCK.sub("", text)
    text = _THINK_TAG.sub("", text)
    return text.strip()


def events_for_turn(
    prompt_text: str,
    completion: Completion,
    count_source: str,
    session_id: Optional[str] = None,
    turn_id: Optional[str] = None,
    user_source: str = "user:local",
    now: Optional[datetime] = None,
    served_from: Optional[str] = None,
    full_input_tokens: Optional[int] = None,
) -> List[AetherEvent]:
    """Construit prompt + completion + token_usage d'un tour deja produit. PUR.
    served_from (ex: 'result-cache') trace qu'un tour a ete servi sans appeler le modele."""
    ts = _now(now)
    turn_id = turn_id or str(uuid.uuid4())
    base = {"turn_id": turn_id, "session_id": session_id}

    prompt_ev = AetherEvent(
        type=EventType.PROMPT, title="prompt", description=prompt_text,
        source=user_source, observed_at=ts, data={**base, "text": prompt_text},
    )
    ctext = strip_think(completion.text)
    completion_ev = AetherEvent(
        type=EventType.COMPLETION, title="completion", description=ctext,
        source=f"llm:{completion.model_id}", observed_at=ts,
        data={**base, "model_id": completion.model_id, "text": ctext,
              **({"served_from": served_from} if served_from else {})},
    )
    token_ev = AetherEvent(
        type=EventType.TOKEN_USAGE, title="token_usage", source="meter", observed_at=ts,
        data={
            **base, "model_id": completion.model_id,
            "count_source": count_source,          # D9 : jamais sommer a travers les bases
            "input_tokens": completion.input_tokens,
            "output_tokens": completion.output_tokens,
            "cached_tokens": completion.cached_tokens,
            **({"served_from": served_from} if served_from else {}),
            **({"full_input_tokens": full_input_tokens,
               "saved_input_tokens": max(0, full_input_tokens - completion.input_tokens)}
               if full_input_tokens is not None else {}),
        },
    )
    return [prompt_ev, completion_ev, token_ev]


def capture_turn(
    prompt_text: str,
    backend: Backend,
    session_id: Optional[str] = None,
    user_source: str = "user:local",
    now: Optional[datetime] = None,
) -> List[AetherEvent]:
    """Un tour single-shot : appelle le backend puis journalise. CAPTURE seule."""
    completion = backend.generate(prompt_text)
    return events_for_turn(
        prompt_text, completion, backend.count_source,
        session_id=session_id, user_source=user_source, now=now,
    )
