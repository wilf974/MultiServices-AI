"""Dimension PROJET — resolution NON DESTRUCTIVE (meme doctrine que `source_alias`).

Pourquoi : la `source` est imposee par le CN du certificat (C2) ; elle dit D'OU on ecrit, pas
SUR QUOI. Un poste = une source (`project:maison`), donc tous les projets d'un meme poste sont
melanges et `project_review` ne trouve rien. Le projet reel vit dans le `session_id`.

Choix doctrinal (append-only, C3) : on NE REECRIT JAMAIS le journal. On resout a la LECTURE.
PUR, sans effet de bord.
"""
from __future__ import annotations

from typing import Optional

from typing import Dict

from .source_alias import canonical

# session_id observe -> projet canonique. Correspondance EXACTE (pas de fuzzy) : predictible.
# Etendre ce dict est l'unique geste de gouvernance, comme SOURCE_ALIASES.
SESSION_PROJECTS: Dict[str, str] = {
    "binah": "project:binah",
}

# prefixe de famille de sessions (`<prefixe>` ou `<prefixe>-<chantier>`) -> projet canonique.
# Recensement du 24/07/2026 sur le journal reel : un projet s'etale sur plusieurs sessions datees
# par chantier (17 sessions `multiservice-*` a elle seule). N'y mettre QUE des familles OBSERVEES :
# une regle inventee ferait dire a la memoire ce qu'elle n'a pas vu.
SESSION_PREFIXES: Dict[str, str] = {
    "multiservice": "project:multiservice",
    "logos":        "project:logos",
    "binah":        "project:binah",
    "aetherlife":   "project:aetherlife",
    "lumiere":      "project:lumiere",
    "pentest":      "project:pentest-agent",
    "noesis":       "project:noesis",
    "finetune":     "project:finetune",
}


def project_of(data: Optional[dict], source: Optional[str] = None) -> str:
    """Projet CANONIQUE d'un evenement. `data['project']` explicite fait foi, sinon la
    session le porte (exact puis prefixe de famille). PUR."""
    explicite = (data or {}).get("project")
    if explicite:
        return canonical(explicite)
    session = (data or {}).get("session_id") or ""
    if session in SESSION_PROJECTS:
        return SESSION_PROJECTS[session]
    for prefixe, projet in SESSION_PREFIXES.items():
        if session == prefixe or session.startswith(prefixe + "-"):
            return projet
    return ""


def matches(data: Optional[dict], source: Optional[str], cle: Optional[str]) -> bool:
    """Un event repond-il a la cle de filtrage ? La cle vaut pour une SOURCE (retro-compat,
    C2 intact) OU pour un PROJET resolu. Cle vide -> tout passe. PUR."""
    if not cle:
        return True
    k = canonical(cle)
    if canonical(source).startswith(k):
        return True
    projet = project_of(data, source)
    return bool(projet) and projet.startswith(k)
