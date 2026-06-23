"""Logique pure de l'API REST web (central-only). Aucun effet de bord.
resolve_token : token bearer -> source (registre token->source). Modele de requete remember."""
from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


def resolve_token(token: Optional[str], registry: dict) -> Optional[str]:
    """Retourne la 'source' associee au token, ou None si token absent/inconnu/sans source."""
    if not token:
        return None
    entry = registry.get(token)
    if not isinstance(entry, dict):
        return None
    return entry.get("source") or None


class RememberRequest(BaseModel):
    text: str = Field(min_length=1, max_length=8192)
    kind: str = "note"
    session: str = "web"
