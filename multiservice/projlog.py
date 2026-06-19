"""Journal de DECISIONS du projet — capture du developpement de MultiService IA dans sa propre
memoire (dogfooding : la memoire-pour-LLM se souvient de son propre developpement).

Ecriture append-only, comme la capture de chat (`/correct`, `/note`). La surface MCP reste,
elle, en LECTURE SEULE. Pose un evenement DECISION / CORRECTION / NOTE dans le journal ; par
defaut le MEME journal que lit le MCP, donc `recall`/`brief`/`recent` le voient aussitot.

C2 (provenance) : source explicite. Par defaut `project:local` (decisions humaines) ou
`project:claude` (notes agent) -> le PREFIXE `project:` isole les events du projet du chat eve,
donc `recall(source="project")` est chirurgical (meme journal, pas de melange de domaines).
C3 (bi-temporalite) : une CORRECTION dans la MEME session (= meme `--session`, p.ex. un sujet)
perime les decisions anterieures de cette session. Regrouper decision et correction sous le meme `--session`.

Lancer :
  python -m multiservice.projlog "Adopter Apache-2.0 pour la licence" --kind decision --session licence
  python -m multiservice.projlog "En fait MIT etait trop permissif" --kind correction --session licence
  python -m multiservice.projlog "lessons_learned lit les corrections C3" --kind note --source project:claude
"""
from __future__ import annotations

import argparse
import uuid
from datetime import datetime, timezone
from typing import Optional

from . import config
from .events import AetherEvent, EventType
from .journal import append_events

KINDS = {"decision": EventType.DECISION,
         "correction": EventType.CORRECTION,
         "note": EventType.NOTE}


def make_event(kind: str, text: str, source: str = "project:local",
               session_id: str = "project", now: Optional[datetime] = None) -> AetherEvent:
    """Construit un evenement de journal de projet (decision/correction/note). PUR, C2/C3."""
    if kind not in KINDS:
        raise ValueError(f"kind invalide : {kind} (attendu : {', '.join(KINDS)})")
    if not text or not text.strip():
        raise ValueError("texte vide")
    ts = now or datetime.now(timezone.utc)
    return AetherEvent(
        type=KINDS[kind], title=kind, description=text, source=source, observed_at=ts,
        data={"text": text, "session_id": session_id, "turn_id": str(uuid.uuid4())},
    )


def log(journal_path, kind: str, text: str, source: str = "project:local",
        session_id: str = "project", now: Optional[datetime] = None) -> int:
    """Ajoute l'evenement au journal (append-only). Ecriture humaine/agent, jamais via le MCP."""
    return append_events(journal_path, [make_event(kind, text, source=source,
                                                   session_id=session_id, now=now)])


def main() -> None:
    p = argparse.ArgumentParser(description="Journal de decisions du projet (capture, append-only).")
    p.add_argument("text", help="le texte de la decision / correction / note")
    p.add_argument("--kind", choices=list(KINDS), default="decision")
    p.add_argument("--source", default="project:local",
                   help="provenance C2 ; prefixe 'project:' pour isoler du chat (project:local, project:claude)")
    p.add_argument("--session", default="project", dest="session_id",
                   help="regroupe un fil (sujet/feature) ; une correction y perime les decisions anterieures")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    a = p.parse_args()
    n = log(a.journal, a.kind, a.text, source=a.source, session_id=a.session_id)
    print(f"[projlog] {a.kind} journalise ({n} evt, session={a.session_id}) -> {a.journal}")


if __name__ == "__main__":
    main()
