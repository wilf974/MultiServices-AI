"""Effacement RGPD crash-safe (crypto-shred) — cf. docs/ENCRYPTION-AT-REST.md sec.5.

Ordre canonique intent-first (WAL) : ① append event `erasure` (intent durable & tamper-evident, C1) ->
② detruire le materiel-cle (idempotent) -> ③ purger l'index PAR event_id (deploie slot -> event_ids, ⑤).
Completude RGPD = `integrity.verify_keyring().ok` (etat reel des cles), pas la presence de l'event.

`erase_resume` (au boot / dans status) rejoue ②+③ sur les cibles `incomplete` — JAMAIS ① (intent deja la).
Convergence plutot qu'atomicite multi-fichiers : le systeme tend vers « intent journalise => cle absente
=> vecteur absent ».
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import List

from . import envelope
from .events import AetherEvent, EventType
from .journal import append_events, read_events


def _events_of_slot(events):
    m = defaultdict(set)
    for e in events:
        if envelope.is_encrypted(e):
            m[e.data["enc"]["slot"]].add(e.id)
    return m


def _needed_ids(events):
    return {e.id for e in events if envelope.is_encrypted(e)}


def _target_event_ids(target, events_of_slot, needed_ids):
    """Une cible d'effacement -> les event_ids concernes (pour purger l'index, indexe par event_id)."""
    if target in events_of_slot:
        return set(events_of_slot[target])               # slot -> ses events
    if target in needed_ids:
        return {target}                                  # event_id -> lui-meme
    return set()


def erase(target: str, km, journal_path: str | Path, embed_store,
          events: List[AetherEvent], authorized_by: str = "human:operator",
          reason: str = "rgpd_art17") -> None:
    """Efface un slot (source/personne) OU un event (fait). `events` = etat AVANT l'append (pour deployer)."""
    append_events(journal_path, [AetherEvent(                # ① intent d'abord (WAL, C1)
        type=EventType.ERASURE, title="erasure", source=authorized_by,
        data={"targets": [target], "reason": reason, "authorized_by": authorized_by})])
    km.destroy(target)                                       # ② detruire la cle (idempotent)
    ev_of_slot, needed = _events_of_slot(events), _needed_ids(events)
    for eid in _target_event_ids(target, ev_of_slot, needed):   # ③ purger l'index PAR event_id (⑤)
        embed_store.evict(eid)


def erase_resume(events: List[AetherEvent], km, embed_store) -> None:
    """Reprise idempotente : rejoue ②+③ sur les cibles `incomplete`, jamais ①."""
    from . import integrity

    ev_of_slot, needed = _events_of_slot(events), _needed_ids(events)
    for t in integrity.verify_keyring(events, km, embed_store)["incomplete"]:
        km.destroy(t)
        for eid in _target_event_ids(t, ev_of_slot, needed):
            embed_store.evict(eid)
