"""Sauvegarde hors-ligne du KEYRING, chiffree par PASSPHRASE.

Le keyring est le point de defaillance unique du chiffrement : perdre `master.key` (32 octets),
c'est perdre tous les snapshots chiffres — aucune reconstruction n'est possible, c'est tout
l'interet du wrapped-DEK. Il faut donc une copie ailleurs. Mais un secret copie n'importe ou est
lui-meme un risque : ce bundle est chiffre sous une cle derivee d'une passphrase (scrypt), donc
stockable sur un cloud, un mail ou un disque partage sans rien exposer.

    python -m multiservice.keyring_backup --out E:\\coffre\\keyring-20260724.bundle
    python -m multiservice.keyring_backup --restore <bundle> --dest ~/.aethercore/keyring

La passphrase est demandee INTERACTIVEMENT (jamais en argument : la ligne de commande se retrouve
dans l'historique du shell et la liste des processus).

REGLE DE PLACEMENT : ne jamais poser le keyring EN CLAIR sur le meme support que les donnees
qu'il protege. Le bundle chiffre, lui, peut aller partout.
"""
from __future__ import annotations

import argparse
import base64
import getpass
import json
import os
from pathlib import Path

from . import config, crypto

VERSION = 1
_b64 = lambda b: base64.b64encode(b).decode()
_ub64 = lambda s: base64.b64decode(s)
_AAD = b"keyring-bundle-v1"


def _collecte(keyring_dir: Path) -> dict:
    """Materiel-cle du keyring : master + tous les slots. PUR (lecture seule)."""
    master = (keyring_dir / "master.key")
    slots_dir = keyring_dir / "slots"
    return {
        "master": _b64(master.read_bytes()) if master.exists() else None,
        "slots": {p.name: p.read_text(encoding="utf-8")
                  for p in sorted(slots_dir.glob("*.key"))} if slots_dir.exists() else {},
    }


def export_bundle(keyring_dir: str | Path, passphrase: str) -> bytes:
    """Bundle chiffre du keyring. Sel et nonce NEUFS a chaque export."""
    if not passphrase or not passphrase.strip():
        raise ValueError("passphrase vide : le bundle ne serait qu'un keyring en clair")
    contenu = json.dumps(_collecte(Path(keyring_dir)), sort_keys=True).encode("utf-8")
    salt, nonce = crypto.gen_salt(), crypto.gen_nonce()
    cle = crypto.derive_key(passphrase, salt)
    ct = crypto.aead_encrypt(cle, nonce, contenu, _AAD)
    return json.dumps({
        "v": VERSION, "alg": "AESGCM", "kdf": "scrypt",
        "n": crypto.SCRYPT_N, "r": crypto.SCRYPT_R, "p": crypto.SCRYPT_P,
        "salt": _b64(salt), "nonce": _b64(nonce), "ct": _b64(ct),
    }, sort_keys=True).encode("utf-8")


def import_bundle(blob: bytes, passphrase: str, dest: str | Path) -> dict:
    """Restaure le keyring depuis un bundle. Leve `crypto.InvalidTag` si la passphrase est fausse."""
    o = json.loads(blob.decode("utf-8"))
    cle = crypto.derive_key(passphrase, _ub64(o["salt"]),
                            n=o.get("n", crypto.SCRYPT_N), r=o.get("r", crypto.SCRYPT_R),
                            p=o.get("p", crypto.SCRYPT_P))
    contenu = json.loads(crypto.aead_decrypt(cle, _ub64(o["nonce"]), _ub64(o["ct"]), _AAD))
    dest = Path(dest)
    (dest / "slots").mkdir(parents=True, exist_ok=True)
    if contenu.get("master"):
        p = dest / "master.key"
        p.write_bytes(_ub64(contenu["master"]))
        try:
            os.chmod(p, 0o600)                      # best-effort (no-op notable sur Windows)
        except OSError:
            pass
    for nom, texte in contenu.get("slots", {}).items():
        (dest / "slots" / nom).write_text(texte, encoding="utf-8")
    return {"master": bool(contenu.get("master")), "slots": len(contenu.get("slots", {}))}


def main() -> int:
    p = argparse.ArgumentParser(description="Sauvegarde chiffree du keyring (passphrase).")
    p.add_argument("--keyring", default=config.KEYRING_DIR)
    p.add_argument("--out", default=None, help="fichier bundle a ecrire")
    p.add_argument("--restore", default=None, metavar="BUNDLE")
    p.add_argument("--dest", default=None, help="dossier keyring cible (restauration)")
    a = p.parse_args()

    if a.restore:
        phrase = getpass.getpass("passphrase du bundle : ")
        dest = a.dest or a.keyring
        r = import_bundle(Path(a.restore).read_bytes(), phrase, dest)
        print("[keyring] restaure -> %s (master=%s, %d slot(s))" % (dest, r["master"], r["slots"]))
        return 0

    if not a.out:
        p.error("--out (export) ou --restore (restauration) est requis")
    phrase = getpass.getpass("passphrase du bundle : ")
    if phrase != getpass.getpass("confirmer : "):
        print("[keyring] les passphrases different : rien ecrit.")
        return 1
    blob = export_bundle(a.keyring, phrase)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(blob)
    print("[keyring] bundle chiffre -> %s (%d octets)" % (out, len(blob)))
    print("[keyring] SANS la passphrase, ce fichier est inutilisable. Notez-la hors machine.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
