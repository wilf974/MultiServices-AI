"""Sprint 18 - Pre-chauffage : estimer le COUT du PROCHAIN tour (LECTURE SEULE).

Esprit Predictive N0 (AetherCore) : on ESTIME, on contextualise, on cite ses preuves. On
N'APPELLE aucun modele, on NE CREE aucun evenement, on NE MUTE RIEN. C'est une projection
(comme le proxy de re-envoi de S15), pas une verite.

Methode : une session de chat est une boule de neige (chaque tour re-envoie le contexte
anterieur). On lit la trajectoire des tokens d'entree de la session, on en deduit la PENTE
(croissance moyenne par tour) et on projette le tour suivant. On contraste deux regimes :
  - snowball continue  : l'entree grossit a la pente observee,
  - fenetrage C3       : compose(keep_turns) borne le contexte -> entree quasi-constante.
L'ecart = l'economie que le fenetrage acheterait au prochain tour.

Construit sur inspect.summarize. Sorties console ASCII.
Lancer : python -m multiservice.preheat   (ou --session <id>)
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional

from . import config
from .events import AetherEvent
from .inspect import summarize
from .journal import read_events


def forecast_next_turn(events: List[AetherEvent], session_id: Optional[str] = None,
                       keep_turns: int = None) -> Dict[str, Any]:
    """Projette le cout du prochain tour d'une session. PUR, LECTURE SEULE, estimation.
    session_id=None -> la session du dernier tour observe. Cite ses preuves (trajectoire, pente)."""
    keep_turns = keep_turns if keep_turns is not None else config.KEEP_TURNS
    summary = summarize(events)
    ordered = summary["turns"]
    sessions = {s["session_id"]: s for s in summary["sessions"]}
    if not ordered:
        return {"found": False, "reason": "aucun tour observe"}
    if session_id is None:
        session_id = ordered[-1]["session_id"]          # session du dernier tour
    s = sessions.get(session_id)
    if s is None:
        return {"found": False, "session_id": session_id, "reason": "session inconnue"}

    inputs: List[int] = s["inputs"]
    n = len(inputs)
    last_in = inputs[-1] if inputs else 0
    deltas = [inputs[i] - inputs[i - 1] for i in range(1, n)]
    growth = (sum(deltas) / len(deltas)) if deltas else 0.0     # pente moyenne du snowball
    avg_out = round(s["out"] / n) if n else 0

    projected_in = max(last_in, round(last_in + growth))        # snowball continue

    # CLASSIFICATION DE REGIME (durci apres le reel, 19 juin) : la formule "fenetrage ~ pente x
    # keep_turns" n'est valable QUE si la session SNOWBALLE (la pente = taille marginale d'un tour).
    # Si l'entree plafonne (deja fenetree / plate), la pente est du bruit autour du plateau et la
    # formule inventerait une economie inexistante. On ne reclame d'economie qu'en accumulation.
    threshold = (last_in / (2 * keep_turns)) if keep_turns else last_in
    snowballing = growth > 0 and growth > threshold
    if snowballing:
        windowed_in = round(growth * keep_turns)                # ~ keep_turns tours marginaux
        regime = "snowball (contexte en accumulation)"
    else:
        windowed_in = projected_in                              # deja borne : le fenetrage ne gagne rien
        regime = "contexte deja borne / plat (peu a gagner par fenetrage)"
    saving = max(0, projected_in - windowed_in)

    return {
        "found": True,
        "session_id": session_id,
        "observed_turns": n,
        "last_input": last_in,
        "avg_growth_per_turn": round(growth, 1),
        "regime": regime,
        "projected_next_input": projected_in,
        "projected_next_output": avg_out,
        "projected_next_total": projected_in + avg_out,
        "keep_turns": keep_turns,
        "projected_windowed_input": windowed_in,
        "windowing_would_save": saving,
        "evidence_inputs_tail": inputs[-6:],                    # preuve : la trajectoire recente
        "basis": "estimation (pente du snowball observe) - lecture seule, aucun appel modele",
    }


def format_report(f: Dict[str, Any]) -> str:
    if not f.get("found"):
        return f"Pre-chauffage: rien a projeter ({f.get('reason', 'inconnu')})."
    L = ["Pre-chauffage: prochain tour (S18 - estimation, lecture seule)"]
    L.append("-" * 64)
    L.append(f"  session {str(f['session_id'])[:8]}  tours observes={f['observed_turns']}")
    L.append(f"  trajectoire entree (queue) : {f['evidence_inputs_tail']}")
    L.append(f"  pente moyenne / tour       : {f['avg_growth_per_turn']} tokens")
    L.append(f"  regime                     : {f['regime']}")
    L.append("-" * 64)
    L.append(f"  PROJECTION prochain tour : in~{f['projected_next_input']}  "
             f"out~{f['projected_next_output']}  total~{f['projected_next_total']}")
    if f["windowing_would_save"] > 0:
        L.append(f"  Fenetrage C3 (keep_turns={f['keep_turns']}) : in~{f['projected_windowed_input']} "
                 f"-> epargnerait ~{f['windowing_would_save']} tokens d'entree")
    else:
        L.append(f"  Fenetrage C3 (keep_turns={f['keep_turns']}) : ~0 a gagner (contexte deja borne)")
    L.append("-" * 64)
    L.append("  (estimation - n'engage rien, n'appelle aucun modele, ne mute rien)")
    return "\n".join(L)


def main() -> None:
    p = argparse.ArgumentParser(description="Pre-chauffage S18 : cout du prochain tour (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--session", default=None, help="session_id (defaut : derniere session)")
    args = p.parse_args()
    f = forecast_next_turn(read_events(args.journal), session_id=args.session)
    print(format_report(f))


if __name__ == "__main__":
    main()
