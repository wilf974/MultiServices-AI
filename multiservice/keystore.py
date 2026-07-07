"""Stockage des `wrapped_dek` derriere l'interface KeyStore (decision ⑦).

Materiel-cle DESTRUCTIBLE, hors-journal, mutable, jamais scelle. Deux impls interchangeables (choix par
config) : `FileKeyStore` (fichier-par-event, defaut P0, corpus ~2k) ; `LogKeyStore` (crypto-shred recursif,
a l'echelle) — DIFFERE. Le code P0 ne connait que l'interface.

Un `wrapped_dek` = DEK d'un event enveloppee sous la KEK de son slot : {slot, nonce, ct}. Le detruire
(shred fin) rend cet event seul illisible ; la ligne du journal ne bouge pas.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Protocol, Set, Tuple


class KeyMissing(Exception):
    """Materiel-cle absent (slot ou dek shredde) -> effacement LEGITIME, pas une attaque."""


class KeyStore(Protocol):
    def has_dek(self, event_id: str) -> bool: ...
    def get_dek(self, event_id: str) -> Tuple[bytes, bytes]: ...        # (nonce, wrapped)
    def slot_of(self, event_id: str) -> str: ...
    def put_dek(self, event_id: str, slot_id: str, nonce: bytes, wrapped: bytes) -> None: ...
    def destroy_dek(self, event_id: str) -> None: ...                  # IDEMPOTENT, destruction REELLE
    def present_deks(self) -> Set[str]: ...


_b64 = lambda b: base64.b64encode(b).decode()
_ub64 = lambda s: base64.b64decode(s)


class FileKeyStore:
    """Un fichier `wrapped/<event_id>.dek` par event. Shred = unlink (destruction atomique, verifiable)."""

    def __init__(self, base: str | Path) -> None:
        self.dir = Path(base) / "wrapped"

    def _p(self, event_id: str) -> Path:
        return self.dir / f"{event_id}.dek"

    def has_dek(self, event_id: str) -> bool:
        return self._p(event_id).exists()

    def get_dek(self, event_id: str) -> Tuple[bytes, bytes]:
        p = self._p(event_id)
        if not p.exists():
            raise KeyMissing(event_id)
        o = json.loads(p.read_text(encoding="utf-8"))
        return _ub64(o["nonce"]), _ub64(o["ct"])

    def slot_of(self, event_id: str) -> str:
        p = self._p(event_id)
        if not p.exists():
            raise KeyMissing(event_id)
        return json.loads(p.read_text(encoding="utf-8"))["slot"]

    def put_dek(self, event_id: str, slot_id: str, nonce: bytes, wrapped: bytes) -> None:
        self.dir.mkdir(parents=True, exist_ok=True)
        self._p(event_id).write_text(
            json.dumps({"slot": slot_id, "nonce": _b64(nonce), "ct": _b64(wrapped)}), encoding="utf-8")

    def destroy_dek(self, event_id: str) -> None:
        try:
            self._p(event_id).unlink()                    # unlink missing-ok -> idempotent
        except FileNotFoundError:
            pass

    def present_deks(self) -> Set[str]:
        if not self.dir.exists():
            return set()
        return {p.stem for p in self.dir.glob("*.dek")}
