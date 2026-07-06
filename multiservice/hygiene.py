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

# En-deca de cette longueur, un texte a segment de gabarit EST le gabarit (commande courte
# collee sans remplir). Au-dela, c'est un doc reel : gabarit seulement si les <...> DOMINENT.
_SHORT_LEN = 80
_DOMINANCE = 0.5

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
    Rejette : un segment <...> a mot de gabarit QUI DOMINE le texte (court, ou >= 50 %).
    Laisse passer : <think>, <div>, 10 < 20, tout texte redige, ET un vrai doc qui
    DOCUMENTE des exemples <...> noyes (faux positif observe : un RUNBOOK)."""
    s = (text or "").strip()
    if not s:
        return True
    hits = [m for m in _SEGMENT_RE.finditer(s)
            if any(w in _fold(m.group(1)) for w in PLACEHOLDER_WORDS)]
    if not hits:
        return False
    if len(s) <= _SHORT_LEN:                 # court + segment de gabarit -> gabarit
        return True
    covered = sum(len(m.group(0)) for m in hits)   # les <...> dominent-ils le doc ?
    return covered / len(s) >= _DOMINANCE
