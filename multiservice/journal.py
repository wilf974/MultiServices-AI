"""Journal-verite append-only (JSONL). Coquille a effet de bord, ISOLEE au bord.

On n'ECRASE jamais, on n'efface jamais : on append. (C3 : cloture, pas suppression.)

Concurrence (capture / ingest / remember / sync peuvent viser le meme fichier) : l'ecriture est
serialisee par un VERROU inter-processus cross-plateforme (fichier .lock en O_EXCL) et faite en UNE
seule ecriture ; la lecture tolere une derniere ligne PARTIELLE (ecriture en cours), sans jamais
masquer une corruption au milieu.
"""
from __future__ import annotations

import json  # noqa: F401  (garde l'API stable pour les imports existants)
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import List

from .events import AetherEvent


@contextmanager
def _file_lock(target: Path, timeout: float = 10.0, stale: float = 60.0):
    """Verrou inter-processus simple, cross-plateforme (Windows + POSIX) : un fichier `<target>.lock`
    cree en O_EXCL sert de mutex. Un verrou perime (> `stale` s, ex. process crashe) est vole."""
    lock = Path(str(target) + ".lock")
    lock.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.close(fd)
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > stale:
                    os.unlink(str(lock))                       # verrou perime -> on le vole
                    continue
            except OSError:
                pass
            if time.monotonic() > deadline:
                raise TimeoutError(f"journal verrouille : {lock}")
            time.sleep(0.02)
    try:
        yield
    finally:
        try:
            os.unlink(str(lock))
        except OSError:
            pass


_AUTO = object()          # sentinelle : keyring pilote par config.ENCRYPT_AT_REST (opt-in global)

# Intents d'audit JAMAIS chiffres : les chiffrer sous le slot qu'ils effacent/migrent detruirait
# la trace en meme temps que la cle (verify_keyring crierait « censure » sur un effacement legitime).
_CLEAR_TYPES = frozenset({"erasure", "migration"})


def _config_keyring():
    """KeyManager par defaut si l'opt-in chiffrement est actif, sinon None. Lu a l'appel (testable)."""
    from . import config
    if not config.ENCRYPT_AT_REST:
        return None
    from .keyring import KeyManager
    return KeyManager()


def default_slot(e: AetherEvent) -> str:
    """Slot-par-source (defaut du design) : effacement gros = toute une source/personne."""
    return f"slot:{e.source}"


def append_events(path: str | Path, events: List[AetherEvent], *, keyring=_AUTO, slot_for=None) -> int:
    """Ajoute des evenements en fin de journal (sous verrou, en UNE ecriture). Retourne le nombre ecrit.

    Opt-in chiffrement (choke point) : si un keyring est actif (config.ENCRYPT_AT_REST ou `keyring`
    explicite), chaque event est chiffre AVANT serialisation (slot-par-source par defaut). Restent en
    clair : les events deja chiffres par l'appelant et les intents d'audit (`erasure`/`migration`).
    `keyring=None` force l'ecriture brute."""
    if keyring is _AUTO:
        keyring = _config_keyring()
    if keyring is not None:
        from . import envelope
        from .encrypt import encrypt_event
        slot_for = slot_for or default_slot
        events = [e if envelope.is_encrypted(e) or e.type.value in _CLEAR_TYPES
                  else encrypt_event(e, slot_for(e), keyring) for e in events]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    blob = "".join(e.model_dump_json() + "\n" for e in events)
    with _file_lock(p):
        with p.open("a", encoding="utf-8") as f:
            f.write(blob)                                      # une seule ecriture : pas d'entrelacement de lignes
            f.flush()
    return len(events)


def read_events(path: str | Path, *, keyring=_AUTO) -> List[AetherEvent]:
    """Relit le journal (pour tests / replay). Vide si absent. Tolere une DERNIERE ligne partielle
    (ecriture concurrente en cours) ; leve sur une ligne corrompue AU MILIEU (jamais masquee).

    `keyring` : par defaut, pilote par config.ENCRYPT_AT_REST (opt-in global) — si actif, chaque event
    chiffre est dechiffre (ou rendu en tombstone si sa cle a ete shreddee, cf.
    `encrypt.decrypt_or_tombstone`). `keyring=None` force la lecture BRUTE (les events chiffres restent
    chiffres) ; un KeyManager explicite outrepasse la config. Un journal en clair n'est jamais affecte."""
    if keyring is _AUTO:
        keyring = _config_keyring()
    p = Path(path)
    if not p.exists():
        return []
    lines = [ln for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip()]
    out: List[AetherEvent] = []
    for i, line in enumerate(lines):
        try:
            out.append(AetherEvent.model_validate_json(line))
        except Exception:
            if i == len(lines) - 1:
                break                                          # derniere ligne partielle -> on l'ignore
            raise                                              # corruption au milieu -> on ne masque pas
    if keyring is not None:
        from .encrypt import decrypt_or_tombstone              # lazy : evite le couplage a l'import
        out = [decrypt_or_tombstone(e, keyring) for e in out]
    return out
