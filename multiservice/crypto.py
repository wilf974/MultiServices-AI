"""SEUL module qui importe `cryptography` (PyCA) — comme `backends.py` isole l'inference.

Primitives PURES bytes->bytes : AEAD (AES-GCM) pour le contenu, wrap/unwrap de cle (KEK-wrappe-DEK).
Zero I/O, zero schema, zero notion d'AetherEvent. Ne JAMAIS rouler d'AEAD maison ailleurs : tout passe
par ici. `InvalidTag` est re-exporte pour que le reste du code ne depende pas de `cryptography`.
"""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag as _InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

NONCE = 12
KEY = 32
SALT = 16

# scrypt : couteux en MEMOIRE, donc resistant au materiel dedie (GPU/ASIC) — ce qu'un simple
# hachage iteratif n'est pas. Parametres interactifs recommandes (~64 Mo, quelques dixiemes de s).
SCRYPT_N = 2 ** 16
SCRYPT_R = 8
SCRYPT_P = 1

InvalidTag = _InvalidTag           # re-export : le reste du code attrape `crypto.InvalidTag`

_WRAP_AAD = b"dek-wrap"            # domaine de separation pour le wrap de cle


def gen_key() -> bytes:
    return os.urandom(KEY)


def gen_nonce() -> bytes:
    return os.urandom(NONCE)


def gen_salt() -> bytes:
    return os.urandom(SALT)


def derive_key(passphrase: str, salt: bytes, n: int = SCRYPT_N, r: int = SCRYPT_R,
               p: int = SCRYPT_P) -> bytes:
    """Derive une cle de 32 octets depuis une PASSPHRASE humaine (scrypt). Sel obligatoire.

    Sert la sauvegarde hors-ligne du keyring : une passphrase memorisable protege un bundle
    stockable n'importe ou. Les parametres voyagent avec le bundle pour rester dechiffrable
    si les defauts changent."""
    return Scrypt(salt=salt, length=KEY, n=n, r=r, p=p).derive(passphrase.encode("utf-8"))


def aead_encrypt(key: bytes, nonce: bytes, pt: bytes, aad: bytes) -> bytes:
    """Chiffre `pt` sous `key`/`nonce`, authentifie `aad`. Retourne ct+tag."""
    return AESGCM(key).encrypt(nonce, pt, aad)


def aead_decrypt(key: bytes, nonce: bytes, ct: bytes, aad: bytes) -> bytes:
    """Dechiffre. Leve `InvalidTag` si `aad` ou `ct` a ete falsifie."""
    return AESGCM(key).decrypt(nonce, ct, aad)


def wrap_key(kek: bytes, dek: bytes) -> tuple[bytes, bytes]:
    """Enveloppe une DEK sous une KEK. Retourne (nonce, wrapped)."""
    n = gen_nonce()
    return n, AESGCM(kek).encrypt(n, dek, _WRAP_AAD)


def unwrap_key(kek: bytes, nonce: bytes, wrapped: bytes) -> bytes:
    """Deballe une DEK. Leve `InvalidTag` si la KEK est fausse ou le blob falsifie."""
    return AESGCM(kek).decrypt(nonce, wrapped, _WRAP_AAD)
