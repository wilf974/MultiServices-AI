"""Registre d'alias de SOURCES — normalisation NON DESTRUCTIVE de la cle de routage (C2).

Pourquoi : quand plusieurs machines / agents / GPT ecrivent dans le meme journal, la `source`
devient une cle de routage structurelle. Des graphies divergentes d'un meme projet
(`project:MultiService-IA` vs `project:multiservice` vs `project:multiservice IA`) fragmentent
recall/recent/brief et faussent toute analytique.

Choix doctrinal (append-only, C3) : on NE REECRIT JAMAIS le journal. On reconcilie a deux endroits :
  - ECRITURE (goulot `projlog.make_event`) : canonicalise la source des FUTURS events.
  - LECTURE (`memory.recall`) : compare les formes CANONIQUES, donc un filtre retrouve aussi
    les events historiques ecrits sous l'ancienne graphie. Le log brut reste intact.

PUR, sans effet de bord. Mapping par correspondance EXACTE (pas de fuzzy) : predictible.
Forme canonique = minuscules, sans espace. Etendre ce dict est l'unique geste de gouvernance.
"""
from __future__ import annotations

from typing import Dict, Optional

# graphie observee -> forme canonique. Seules les VRAIES graphies d'un meme projet y figurent.
# NE PAS y mettre : les sources de capture (user:/llm:/meter/agent:), les env distincts
# (project:logos-staging), ni les decisions fondatrices (project:local laisse tel quel).
SOURCE_ALIASES: Dict[str, str] = {
    "project:MultiService-IA": "project:multiservice",
    "project:multiservice IA": "project:multiservice",
    "project:AetherCore":      "project:aethercore",
    "project:Logos":           "project:logos",
}


def canonical(source: Optional[str]) -> str:
    """Forme canonique d'une source. Correspondance exacte ; inconnu -> inchange. PUR.
    Entree vide/None -> "" (jamais d'exception : ne doit jamais casser une ecriture ou un filtre)."""
    if not source:
        return ""
    return SOURCE_ALIASES.get(source, source)
