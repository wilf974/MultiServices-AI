"""Keyring — materiel-cle DESTRUCTIBLE hors-journal (master + KEK_slot), composant un KeyStore (deks).

Hierarchie a 3 niveaux (design ⑦) :
  Master (32B, 0600)  ── wrappe ──►  KEK_slot (slots/<h>.key)  ── wrappe ──►  wrapped_dek (KeyStore)  ── chiffre ──►  contenu
Rotation master = re-wrap des KEK_slot ; rotation slot = re-wrap des wrapped_dek du slot. JAMAIS de
re-chiffrement du contenu ni de reecriture du journal (c'est tout l'interet du wrapped-DEK hors-ligne).

Effacement (crypto-shred) : detruire un fichier de cle -> l'event (ou le slot) devient illisible, la ligne
du journal ne bouge pas. `destroy(target)` accepte un slot_id OU un event_id (idempotent, missing-ok).
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
from typing import Set, Tuple

from . import config, crypto
from .keystore import FileKeyStore, KeyMissing

_b64 = lambda b: base64.b64encode(b).decode()
_ub64 = lambda s: base64.b64decode(s)


class KeyManager:
    """Facade sur master + slots (keyring) + deks (KeyStore). C'est le `kr` du design."""

    def __init__(self, base: str | Path | None = None, keystore=None) -> None:
        self.base = Path(base) if base is not None else Path(config.AETHER_HOME) / "keyring"
        self.master_path = self.base / "master.key"
        self.slots_dir = self.base / "slots"
        self.keystore = keystore or FileKeyStore(self.base)

    # --- master ---
    def _master(self) -> bytes:
        if not self.master_path.exists():
            self.base.mkdir(parents=True, exist_ok=True)
            self._write_master(crypto.gen_key())
        return self.master_path.read_bytes()

    def _write_master(self, key: bytes) -> None:
        self.base.mkdir(parents=True, exist_ok=True)
        self.master_path.write_bytes(key)
        try:
            os.chmod(self.master_path, 0o600)             # best-effort (no-op notable sur Windows)
        except OSError:
            pass

    # --- slots (KEK_slot wrappee sous master) ---
    def _slot_path(self, slot_id: str) -> Path:
        h = hashlib.sha256(slot_id.encode("utf-8")).hexdigest()
        return self.slots_dir / f"{h}.key"

    def has_slot(self, slot_id: str) -> bool:
        return self._slot_path(slot_id).exists()

    def get_slot(self, slot_id: str) -> bytes:
        p = self._slot_path(slot_id)
        if not p.exists():
            raise KeyMissing(slot_id)
        o = json.loads(p.read_text(encoding="utf-8"))
        return crypto.unwrap_key(self._master(), _ub64(o["nonce"]), _ub64(o["ct"]))

    def _put_slot(self, slot_id: str, kek: bytes) -> None:
        self.slots_dir.mkdir(parents=True, exist_ok=True)
        n, ct = crypto.wrap_key(self._master(), kek)
        self._slot_path(slot_id).write_text(json.dumps({"nonce": _b64(n), "ct": _b64(ct)}), encoding="utf-8")

    def get_or_create_slot(self, slot_id: str) -> bytes:
        if self.has_slot(slot_id):
            return self.get_slot(slot_id)
        kek = crypto.gen_key()
        self._put_slot(slot_id, kek)
        return kek

    # --- deks (delegation KeyStore) ---
    def has_dek(self, event_id: str) -> bool:
        return self.keystore.has_dek(event_id)

    def get_dek(self, event_id: str) -> Tuple[bytes, bytes]:
        return self.keystore.get_dek(event_id)

    def put_dek(self, event_id: str, slot_id: str, nonce: bytes, wrapped: bytes) -> None:
        self.keystore.put_dek(event_id, slot_id, nonce, wrapped)

    def present_deks(self) -> Set[str]:
        return self.keystore.present_deks()

    def present_slots(self) -> Set[str]:
        # on ne peut pas inverser le hash -> on expose les hashs presents (usage interne only)
        if not self.slots_dir.exists():
            return set()
        return {p.stem for p in self.slots_dir.glob("*.key")}

    # --- effacement (crypto-shred) ---
    def destroy(self, target: str) -> None:
        """Detruit le materiel-cle d'un slot OU d'un event (idempotent). Un slot et un event_id ne
        collisionnent pas (namespaces distincts) -> tenter les deux est sur."""
        try:
            self._slot_path(target).unlink()              # slot ? (missing-ok)
        except FileNotFoundError:
            pass
        self.keystore.destroy_dek(target)                 # event_id ? (missing-ok, idempotent)

    # --- rotations = RE-WRAP seul, jamais de re-chiffrement du contenu ---
    def rotate_master(self, new_master: bytes) -> None:
        """Re-wrappe chaque KEK_slot sous `new_master`, puis remplace le master. Journal intact."""
        old = self._master()
        keks = {}
        for p in self.slots_dir.glob("*.key") if self.slots_dir.exists() else []:
            o = json.loads(p.read_text(encoding="utf-8"))
            keks[p] = crypto.unwrap_key(old, _ub64(o["nonce"]), _ub64(o["ct"]))
        self._write_master(new_master)
        for p, kek in keks.items():
            n, ct = crypto.wrap_key(new_master, kek)
            p.write_text(json.dumps({"nonce": _b64(n), "ct": _b64(ct)}), encoding="utf-8")

    def rotate_slot(self, slot_id: str) -> None:
        """Nouvelle KEK_slot ; re-wrappe les wrapped_dek du slot sous la nouvelle. Contenu jamais re-chiffre."""
        old_kek = self.get_slot(slot_id)
        new_kek = crypto.gen_key()
        for eid in self.keystore.present_deks():
            if self.keystore.slot_of(eid) != slot_id:
                continue
            n, w = self.keystore.get_dek(eid)
            dek = crypto.unwrap_key(old_kek, n, w)
            n2, w2 = crypto.wrap_key(new_kek, dek)
            self.keystore.put_dek(eid, slot_id, n2, w2)
        self._put_slot(slot_id, new_kek)
