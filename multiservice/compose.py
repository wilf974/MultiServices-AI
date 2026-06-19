"""Sprint 16 etape 2 - Cloture C3 (compaction SANS perte), cote contexte.

Le journal garde TOUT verbatim (append-only, rien supprime). Ici on ne touche QUE le
prompt envoye au modele : on garde le(s) message(s) systeme + les K derniers tours, et on
remplace les plus anciens par un REPERE compact (pointeur). Les tours ecartes restent au
journal, rejouables : c'est la cloture C3 (clore, pas supprimer) appliquee au contexte.

100% PUR : List[Message] -> List[Message]. Aucune mutation de l'entree, aucun effet de bord.
Reglage qualite : keep_turns assez haut pour ne pas amputer le modele (defaut 6).
"""
from __future__ import annotations

from typing import List

from .backends import Message


def compose(messages: List[Message], keep_turns: int = 6, marker: bool = True) -> List[Message]:
    """Retourne le prompt a envoyer : systeme + K derniers tours (+ repere si ecarte).

    Un 'tour' = 2 messages (user + assistant). On garde 2*keep_turns + 1 messages de corps
    (les K paires recentes + le message user courant). En-dessous, on renvoie tout."""
    system = [m for m in messages if m.get("role") == "system"]
    body = [m for m in messages if m.get("role") != "system"]
    keep = keep_turns * 2 + 1
    if len(body) <= keep:
        return list(messages)                      # rien a clore
    dropped = len(body) - keep
    out: List[Message] = list(system)
    if marker:
        out.append({
            "role": "system",
            "content": f"[{dropped} messages anterieurs clotures - presents au journal, "
                       f"hors contexte (cloture C3, rejouables)]",
        })
    out.extend(body[-keep:])
    return out


def dropped_count(messages: List[Message], keep_turns: int = 6) -> int:
    """Combien de messages de corps seraient ecartes (pour mesurer). PUR."""
    body = [m for m in messages if m.get("role") != "system"]
    return max(0, len(body) - (keep_turns * 2 + 1))
