"""Migration chiffrement au repos (design sec.8) — bulk re-encrypt SUPERVISE du stock en clair.

Forward-only (recommande, defaut) : activer `MULTISERVICE_ENCRYPT=1` suffit — les NOUVEAUX events
sont chiffres a l'ecriture (choke point `journal.append_events`), l'ancien clair reste, la chaine
n'est jamais rebaselinee. Cette CLI sans drapeau ne fait qu'un PLAN (dry-run).

Bulk (`--bulk --yes`, C1) : operation supervisee UNIQUE — re-chiffre les events en clair
(slot-par-source), trace un event `migration` EN CLAIR, sauvegarde l'ancien journal + ses sceaux
(`.pre-encrypt.bak` — a detruire selon politique), REBASELINE la chaine (nouveau sceau).
Idempotent : les events deja chiffres (tombstones inclus) sont conserves octet pour octet.
Les index vecteurs restent valides (ids inchanges, embeddings derives du clair) ; la projection
SQLite se reconstruit seule (watermark chain_head divergent -> rebuild force).
"""
from __future__ import annotations

import os
from collections import Counter
from pathlib import Path
from typing import Dict, List

from . import envelope, integrity
from .encrypt import encrypt_event
from .events import AetherEvent, EventType
from .journal import _CLEAR_TYPES, _file_lock, default_slot, read_events


def plan(events: List[AetherEvent]) -> Dict:
    """PUR — ce que ferait un bulk : combien de clair a chiffrer, par source. Ne touche rien."""
    clair = [e for e in events
             if not envelope.is_encrypted(e) and e.type.value not in _CLEAR_TYPES]
    chiffres = sum(1 for e in events if envelope.is_encrypted(e))
    return {"total": len(events), "clair": len(clair), "chiffres": chiffres,
            "intents": len(events) - len(clair) - chiffres,
            "par_source": dict(Counter(e.source for e in clair))}


def migrate_events(events: List[AetherEvent], km, slot_for=default_slot) -> List[AetherEvent]:
    """Chiffre les events en clair (slot-par-source) ; conserve TELS QUELS les deja-chiffres
    (leur enveloppe, donc leurs cles et tombstones) et les intents d'audit (erasure/migration)."""
    return [e if envelope.is_encrypted(e) or e.type.value in _CLEAR_TYPES
            else encrypt_event(e, slot_for(e), km) for e in events]


def bulk_migrate(journal_path: str | Path, km, authorized_by: str = "human:operator",
                 slot_for=default_slot) -> Dict:
    """Bulk re-encrypt supervise (C1). Sous verrou journal : lit BRUT, chiffre le clair, ecrit un
    NOUVEAU journal (+ event `migration` en clair), sauvegarde l'ancien + ses sceaux, re-scelle."""
    p = Path(journal_path)
    with _file_lock(p):
        raw = read_events(p, keyring=None)
        migrated = migrate_events(raw, km, slot_for)
        n = sum(1 for a, b in zip(raw, migrated) if a is not b)
        slots = sorted({e.data["enc"]["slot"] for e in migrated if envelope.is_encrypted(e)})
        trace = AetherEvent(type=EventType.MIGRATION, title="encrypt_migrate",
                            source=authorized_by,
                            data={"migrated": n, "total": len(raw), "slots": slots,
                                  "authorized_by": authorized_by})
        tmp = p.with_name(p.name + ".migrating")
        tmp.write_text("".join(e.model_dump_json() + "\n" for e in migrated + [trace]),
                       encoding="utf-8")
        backup = p.with_name(p.name + ".pre-encrypt.bak")
        os.replace(p, backup)                                   # l'ancien clair : politique humaine
        os.replace(tmp, p)
    seal_path = integrity._seal_path(p)
    if seal_path.exists():                                      # les sceaux de l'ere « clair »
        os.replace(seal_path, seal_path.with_name(seal_path.name + ".pre-encrypt.bak"))
    rec = integrity.seal(p)                                     # nouvelle baseline de chaine
    return {"migrated": n, "total": len(raw), "backup": str(backup), "seal": rec}


def main() -> None:
    import argparse

    from . import config
    from .keyring import KeyManager

    ap = argparse.ArgumentParser(description="Migration chiffrement au repos (dry-run par defaut).")
    ap.add_argument("--journal", default=config.JOURNAL_PATH)
    ap.add_argument("--bulk", action="store_true", help="re-chiffrer le stock en clair (supervise)")
    ap.add_argument("--yes", action="store_true", help="confirmer le bulk (C1 : operation unique)")
    ap.add_argument("--authorized-by", default="human:operator")
    a = ap.parse_args()

    pl = plan(read_events(a.journal, keyring=None))
    print(f"[plan] total={pl['total']} clair={pl['clair']} chiffres={pl['chiffres']} "
          f"intents={pl['intents']} sources={len(pl['par_source'])}")
    if not a.bulk:
        print("[plan] forward-only (recommande) : MULTISERVICE_ENCRYPT=1 chiffre les NOUVEAUX events.")
        print("[plan] pour re-chiffrer le stock : --bulk --yes (rebaseline la chaine, backup du clair).")
        return
    if not a.yes:
        print("[bulk] REFUSE sans --yes (operation supervisee unique, C1).")
        raise SystemExit(2)
    r = bulk_migrate(a.journal, KeyManager(), authorized_by=a.authorized_by)
    print(f"[bulk] migres={r['migrated']}/{r['total']} backup={r['backup']}")
    print(f"[bulk] nouveau sceau : count={r['seal']['count']} head={r['seal']['head'][:16]}...")
    print("[bulk] l'ancien clair est dans le .bak : a detruire selon politique.")


if __name__ == "__main__":
    main()
