"""Hygiene d'ecriture : detecter un GABARIT NON REMPLI avant de le journaliser.

Pollution OBSERVEE dans le journal reel (01/07/2026) : des textes de gabarit copies sans etre
remplis — '<le fait, texte reel>', '<resultat / decision>', 'H3 : <resultat / decision>'.
Regle (Fable5/CLAUDE.md) : « ne jamais journaliser un gabarit non rempli ».

Heuristique VOLONTAIREMENT etroite (calibree sur l'observe, pas inventee — discipline BITS) :
on ne signale que les segments <...> dont le contenu est du vocabulaire de gabarit. Dans le
doute on laisse passer : la memoire observe, le garde-fou n'attrape que l'erreur evidente.
PUR : str -> bool. Le contournement VOLONTAIRE reste possible aux canaux humains
(--force / force=true, esprit C1) ; pas au modele (remember).
"""
from __future__ import annotations

import re
import unicodedata

# Un segment <...> court, sans saut de ligne (un vrai gabarit tient sur sa ligne).
_SEGMENT_RE = re.compile(r"<([^<>\n]{1,80})>")

# Vocabulaire de gabarit (compare sans accents ni casse). Liste courte et explicite :
# ne l'elargir que sur de la pollution reellement observee, jamais a l'aveugle.
PLACEHOLDER_WORDS = (
    "fait", "texte", "text", "txt", "resultat", "decision", "lecon", "note",
    "sujet", "exemple", "placeholder", "todo", "completer", "remplir",
    "observation", "correction", "validation", "hypothese",
)


def _fold(s: str) -> str:
    """Minuscules + accents retires (comparaison stable quelle que soit la saisie). PUR."""
    nfkd = unicodedata.normalize("NFKD", s or "")
    return "".join(c for c in nfkd if not unicodedata.combining(c)).lower()


def looks_like_placeholder(text: str) -> bool:
    """Vrai si `text` est vide ou ressemble a un gabarit NON REMPLI. PUR, etroit.
    Rejette : un segment <...> dont le contenu (sans accents) contient un mot de gabarit.
    Laisse passer : <think>, <div>, comparaisons 10 < 20, et tout texte reellement redige."""
    if not (text or "").strip():
        return True
    for m in _SEGMENT_RE.finditer(text):
        inner = _fold(m.group(1))
        if any(w in inner for w in PLACEHOLDER_WORDS):
            return True
    return False
