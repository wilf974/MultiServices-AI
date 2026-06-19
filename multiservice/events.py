"""Schema d'evenements - VENDU depuis aethercore.events pour le scaffold S13.

NOTE D'INTEGRATION : en production, NE PAS dupliquer ce schema. On ETEND
aethercore.events.EventType avec les membres LLM ci-dessous (l'enum est ouvert,
le schema AetherEvent reste inchange - cf. CONCEPTION sec.3/4). Cette copie
existe uniquement pour que le scaffold soit auto-suffisant et testable hors repo.

Invariants portes par le schema :
  C2 - provenance : `source` obligatoire (validateur), `confidence`, `observed_at`.
  C3 - bi-temporalite : `valid_from` toujours pose ; correction = cloture, pas suppression.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


class EventType(str, Enum):
    # --- types AetherCore existants (rappel) ---
    CHANGE = "change"
    INCIDENT = "incident"
    DISCOVERY = "discovery"
    DECISION = "decision"
    NOTE = "note"
    ALERT = "alert"
    # --- types LLM ajoutes par MultiService AI (Sprint 13) ---
    PROMPT = "prompt"
    COMPLETION = "completion"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    CORRECTION = "correction"
    TOKEN_USAGE = "token_usage"
    # --- types de RAISONNEMENT (graphe causal, Memory Intelligence) ---
    HYPOTHESIS = "hypothesis"
    OBSERVATION = "observation"
    VALIDATION = "validation"


# Le perimetre EXACT capture par le Sprint 13 (capture seule).
CAPTURE_TYPES = frozenset({
    EventType.PROMPT, EventType.COMPLETION, EventType.TOOL_CALL,
    EventType.TOOL_RESULT, EventType.CORRECTION, EventType.TOKEN_USAGE,
})


class AetherEvent(BaseModel):
    """Evenement canonique. C2/C3 portes par le schema."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: EventType
    title: str
    description: str = ""
    # C2 - provenance obligatoire
    source: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    observed_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    # C3 - bi-temporalite
    valid_from: Optional[datetime] = None
    valid_to: Optional[datetime] = None
    data: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("source")
    @classmethod
    def source_non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("C2 viole : source obligatoire")
        return v

    def model_post_init(self, __context: Any) -> None:
        if self.valid_from is None:
            self.valid_from = self.observed_at
