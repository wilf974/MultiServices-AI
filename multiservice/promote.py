"""Sprint 17 (fin) - Promotion de skills, HUMAN-GATED.

Transforme une candidate CHOISIE PAR L'HUMAIN en SKILL.md (format Agent Skills ouvert),
versionnee et bi-temporelle (C3 : on n'ecrase pas l'histoire, on archive + on append).

  - promote()  : ecrit SKILL.md + APPEND un evenement DECISION (source=user) au journal.
                 Si une version existe deja, l'ancienne est ARCHIVEE (SKILL.v{n}.md) et la
                 nouvelle DECISION porte 'supersedes' = id de la precedente (lignee).
  - retire()   : APPEND une DECISION de cloture (data.closes), ne supprime jamais le fichier.
  - skill_health() : LECTURE SEULE, 3 signaux de peremption (D11).

Rien ne s'auto-promeut : promote/retire ne sont appeles que par la CLI, sur ordre humain.
On n'efface JAMAIS (C3) ; on n'ecrit au journal que des DECISION humaines (C6).
Les constructeurs (build_skill_md, current_version, skill_health) sont PURS.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from .events import AetherEvent, EventType
from .journal import append_events, read_events
from .skills import _tokens


# --------------------------------------------------------------------------- #
# PUR
# --------------------------------------------------------------------------- #
def build_skill_md(name: str, description: str, body: str, trigger: str = "",
                   evidence: Sequence[str] = (), version: int = 1,
                   created: Optional[datetime] = None) -> str:
    """Construit le contenu SKILL.md (frontmatter YAML + corps). PUR."""
    created = created or datetime.now(timezone.utc)
    fm = [
        "---",
        f"name: {name}",
        f"description: {description}",
        f"version: {version}",
        f"created: {created.isoformat()}",
        f"trigger: {trigger}",
        f"evidence: {', '.join(evidence)}",
        "---",
        "",
    ]
    return "\n".join(fm) + body.rstrip() + "\n"


def _promotions(name: str, events: List[AetherEvent]) -> List[AetherEvent]:
    return [e for e in events if e.type == EventType.DECISION
            and e.data.get("action") == "promote_skill" and e.data.get("skill") == name]


def current_version(name: str, events: List[AetherEvent]) -> int:
    """Nb de versions deja promues pour ce nom. PUR."""
    return len(_promotions(name, events))


def skill_health(name: str, trigger: str, events: List[AetherEvent],
                 evidence: Sequence[str] = (), now: Optional[datetime] = None,
                 blind_days: int = 14) -> Dict[str, Any]:
    """3 signaux de peremption (D11), LECTURE SEULE. PUR.

    (a) fenetre muette : le declencheur n'apparait plus dans les prompts recents ;
    (c) retrecissement de la preuve : evenements-preuve clotures (valid_to) sous C3 ;
    (b) pic de corrections : NON encore mesurable (corrections pas capturees) -> note.
    """
    now = _aware(now or datetime.now(timezone.utc))
    trig = {t for t in _tokens(trigger)} or set(trigger.split("+"))
    last_seen: Optional[datetime] = None
    for e in events:
        if e.type == EventType.PROMPT and (e.source or "").startswith("user"):
            if trig & _tokens(e.data.get("text", "")):
                vf = _aware(e.valid_from) if e.valid_from else None
                if vf and (last_seen is None or vf > last_seen):
                    last_seen = vf
    stale_trigger = last_seen is None or (now - last_seen).days >= blind_days

    ev_ids = set(evidence)
    closed = sum(1 for e in events if e.id in ev_ids and e.valid_to is not None)

    return {
        "skill": name,
        "last_trigger_seen": last_seen.isoformat() if last_seen else None,
        "stale_trigger": stale_trigger,                 # signal (a)
        "evidence_closed": closed,                      # signal (c)
        "correction_spike": None,                       # signal (b) : a venir (corrections non capturees)
        "blind_days": blind_days,
    }


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# ACTIONS (effet de bord ISOLE : fichier SKILL.md + APPEND journal ; jamais d'effacement)
# --------------------------------------------------------------------------- #
def promote(name: str, description: str, body: str, skills_dir: str | Path,
            journal_path: str | Path, trigger: str = "", evidence: Sequence[str] = (),
            now: Optional[datetime] = None) -> AetherEvent:
    """Promotion HUMAINE : ecrit SKILL.md (archive l'ancienne version) + append DECISION."""
    now = now or datetime.now(timezone.utc)
    events = read_events(journal_path)
    prior = _promotions(name, events)
    version = len(prior) + 1

    d = Path(skills_dir) / name
    d.mkdir(parents=True, exist_ok=True)
    cur = d / "SKILL.md"
    if cur.exists():                                   # C3 : on archive, on ne perd rien
        cur.rename(d / f"SKILL.v{version - 1}.md")
    md = build_skill_md(name, description, body, trigger, list(evidence), version, now)
    cur.write_text(md, encoding="utf-8")

    ev = AetherEvent(
        type=EventType.DECISION, title=f"promote skill: {name} v{version}",
        description=description, source="user:wilfred", observed_at=now,
        data={
            "action": "promote_skill", "skill": name, "version": version,
            "trigger": trigger, "evidence": list(evidence)[:8],
            "path": str(cur), "content_sha256": hashlib.sha256(md.encode("utf-8")).hexdigest(),
            **({"supersedes": prior[-1].id} if prior else {}),
        },
    )
    append_events(journal_path, [ev])
    return ev


def retire(name: str, journal_path: str | Path, reason: str = "",
           now: Optional[datetime] = None) -> AetherEvent:
    """Cloture HUMAINE d'une skill (C3) : append une DECISION ; le fichier n'est PAS supprime."""
    now = now or datetime.now(timezone.utc)
    prior = _promotions(name, read_events(journal_path))
    ev = AetherEvent(
        type=EventType.DECISION, title=f"retire skill: {name}",
        description=reason, source="user:wilfred", observed_at=now,
        data={"action": "retire_skill", "skill": name,
              **({"closes": prior[-1].id} if prior else {})},
    )
    append_events(journal_path, [ev])
    return ev


def main() -> None:
    import argparse
    from . import config
    p = argparse.ArgumentParser(description="Promotion de skills S17 (human-gated).")
    p.add_argument("name")
    p.add_argument("--description", default="")
    p.add_argument("--body", default="", help="corps du SKILL.md (texte)")
    p.add_argument("--body-file", default=None, help="fichier dont le contenu sert de corps")
    p.add_argument("--trigger", default="")
    p.add_argument("--evidence", default="", help="ids separes par des virgules")
    p.add_argument("--retire", action="store_true", help="cloturer la skill (C3, sans effacer)")
    p.add_argument("--health", action="store_true", help="diagnostic de peremption (lecture seule)")
    p.add_argument("--skills-dir", default=config.SKILLS_DIR, dest="skills_dir")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    a = p.parse_args()
    evidence = [x for x in a.evidence.split(",") if x.strip()]

    if a.health:
        h = skill_health(a.name, a.trigger, read_events(a.journal), evidence)
        print(f"Sante skill '{a.name}':")
        print(f"  declencheur vu pour la derniere fois : {h['last_trigger_seen']}")
        print(f"  (a) fenetre muette sur le declencheur : {h['stale_trigger']}")
        print(f"  (c) preuves cloturees (C3)            : {h['evidence_closed']}")
        print(f"  (b) pic de corrections                : {h['correction_spike']} (a venir)")
        return
    if a.retire:
        ev = retire(a.name, a.journal, a.description)
        print(f"[retire] '{a.name}' cloture (DECISION {ev.id[:8]}). Le fichier SKILL.md est conserve.")
        return

    body = a.body
    if a.body_file:
        bf = Path(a.body_file)
        if not bf.exists():
            print(f"[erreur] fichier introuvable : {a.body_file}")
            print("        -> donne un chemin valide, ou retire --body-file (un gabarit sera genere).")
            return
        body = bf.read_text(encoding="utf-8")
    if not body.strip():
        body = f"# {a.name}\n\n(Reference promue depuis l'usage observe. Declencheur: {a.trigger})\n"
    ev = promote(a.name, a.description, body, a.skills_dir, a.journal,
                 trigger=a.trigger, evidence=evidence)
    print(f"[promote] '{a.name}' v{ev.data['version']} -> {ev.data['path']}")
    print(f"          DECISION {ev.id[:8]} journalisee (bi-temporelle).")


if __name__ == "__main__":
    main()
