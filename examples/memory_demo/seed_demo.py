"""Journal de DEMO synthetique pour MultiService IA — projet fictif « DunkBot 3000 ».

AUCUNE donnee reelle : un projet maker invente (un robot qui retourne des pancakes) sert a
MONTRER ce que la memoire apporte. On y a glisse expres :
  - une DECISION (moteur NEMA-17) ... puis une CORRECTION qui la perime (servo MG996R) -> C3,
  - une completion avec un BLOC DE CODE (has_code), une autre avec un TABLEAU (has_table),
le tout dans UNE session continue (la correction posterieure perime la decision anterieure).
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # racine du depot
from multiservice.events import AetherEvent, EventType  # noqa: E402

NOW = datetime(2026, 6, 19, 12, 0, tzinfo=timezone.utc)
SESSION = "demo-dunkbot"
QUERY = "Quel moteur DunkBot doit utiliser pour le bras qui retourne les pancakes ?"

FLIP_CODE = (
    "Routine de flip de DunkBot :\n"
    "```python\n"
    "def flip(arm):\n"
    "    arm.rotate(deg=180, speed='snap')    # le coup de poignet\n"
    "    arm.rotate(deg=-180, speed='smooth')\n"
    "```\n"
    "Calibre l'angle a 175 deg si la poele est lourde."
)

PARTS_TABLE = (
    "Nomenclature DunkBot v1 :\n"
    "| Piece | Ref | Role |\n"
    "| :--- | :--- | :--- |\n"
    "| Moteur bras | NEMA-17 | flip |\n"
    "| Chassis | alu T6 | structure |\n"
    "| Capteur | IR | detection du pancake |\n"
)


def _ev(typ: EventType, text: str, source: str, at: datetime, turn_id: str) -> AetherEvent:
    return AetherEvent(type=typ, title=typ.value, description=text, source=source,
                       observed_at=at, data={"text": text, "session_id": SESSION, "turn_id": turn_id})


def build_events() -> list:
    """La petite histoire de DunkBot, en evenements dates (une seule session continue)."""
    return [
        # --- Jour 1 : conception ---
        _ev(EventType.PROMPT, "Quel moteur pour le bras de flip de DunkBot ?",
            "user:maker", NOW - timedelta(days=3), "t1"),
        _ev(EventType.DECISION,
            "DunkBot : bras de flip motorise par un NEMA-17 (pas-a-pas), pour un controle d'angle precis.",
            "user:maker", NOW - timedelta(days=3, seconds=-30), "t1"),
        _ev(EventType.COMPLETION, FLIP_CODE, "llm:eve", NOW - timedelta(days=3, seconds=-120), "t2"),
        _ev(EventType.COMPLETION, PARTS_TABLE, "llm:eve", NOW - timedelta(days=3, seconds=-240), "t3"),
        # --- Jour 3 : le terrain corrige la decision ---
        _ev(EventType.PROMPT, "Le bras cale quand la poele est pleine de pate...",
            "user:maker", NOW - timedelta(days=1), "t4"),
        _ev(EventType.CORRECTION,
            "En fait le moteur NEMA-17 du bras CALE sous le poids de la poele : passer a un "
            "servo a fort couple (MG996R) + reducteur 2:1.",
            "user:maker", NOW - timedelta(days=1, seconds=-30), "t5"),
    ]


def export_json(path: str) -> None:
    """Exporte les evenements en JSON (inspection / autres outils). Donnees fictives, publiables.
    NB : le GUI arcade.html est AUTONOME (il embarque sa propre copie), il ne lit pas ce fichier."""
    import json
    rows = [{
        "id": e.id, "type": e.type.value, "source": e.source,
        "valid_from": e.valid_from.isoformat() if e.valid_from else None,
        "session_id": e.data.get("session_id"), "turn_id": e.data.get("turn_id"),
        "text": e.data.get("text", ""),
    } for e in build_events()]
    with open(path, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"[demo] {len(rows)} evenements fictifs exportes -> {path}")


if __name__ == "__main__":
    out = os.path.join(os.path.dirname(__file__), "demo_events.json")
    export_json(out)
