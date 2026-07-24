"""SEUL module qui importe `cryptography` (PyCA) — comme `backends.py` isole l'inference.

Primitives PURES bytes->bytes : AEAD (AES-GCM) pour le contenu, wrap/unwrap de cle (KEK-wrappe-DEK).
Zero I/O, zero schema, zero notion d'AetherEvent. Ne JAMAIS rouler d'AEAD maison ailleurs : tout passe
par ici. `InvalidTag` est re-exporte pour que le reste du code ne depende pas de `cryptography`.
"""
from __future__ import annotations

import os

from cryptography.exceptions import InvalidTag as _InvalidTag
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (X25519PrivateKey,
                                                              X25519PublicKey)
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
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


# --- asymetrique (X25519) : chiffrer sur une machine qui ne doit PAS pouvoir dechiffrer ---
_SEAL_INFO = b"multiservice-snapshot-seal-v1"
_SEAL_AAD = b"snapshot-seal"


def gen_keypair() -> tuple[bytes, bytes]:
    """Paire X25519 -> (privee, publique), en octets bruts. La PRIVEE ne quitte pas le poste."""
    sk = X25519PrivateKey.generate()
    priv = sk.private_bytes(encoding=serialization.Encoding.Raw,
                            format=serialization.PrivateFormat.Raw,
                            encryption_algorithm=serialization.NoEncryption())
    pub = sk.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                       format=serialization.PublicFormat.Raw)
    return priv, pub


def _derive_shared(shared: bytes) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=KEY, salt=None, info=_SEAL_INFO).derive(shared)


def seal_to_public(pub: bytes, secret: bytes) -> bytes:
    """Scelle `secret` vers une cle PUBLIQUE (schema ECIES : X25519 ephemere + HKDF + AES-GCM).
    Le detenteur de la seule publique peut sceller, JAMAIS ouvrir. Cle ephemere neuve a chaque
    appel -> deux scellements du meme secret different."""
    eph = X25519PrivateKey.generate()
    partagee = _derive_shared(eph.exchange(X25519PublicKey.from_public_bytes(pub)))
    nonce = gen_nonce()
    ct = AESGCM(partagee).encrypt(nonce, secret, _SEAL_AAD)
    epk = eph.public_key().public_bytes(encoding=serialization.Encoding.Raw,
                                        format=serialization.PublicFormat.Raw)
    return epk + nonce + ct                       # 32 + 12 + n : format fixe, pas d'ambiguite


def open_with_private(priv: bytes, blob: bytes) -> bytes:
    """Ouvre un scelle avec la cle PRIVEE. Leve `InvalidTag` si ce n'est pas la bonne."""
    if len(blob) < 32 + NONCE:
        raise ValueError("scelle trop court")
    epk, nonce, ct = blob[:32], blob[32:32 + NONCE], blob[32 + NONCE:]
    sk = X25519PrivateKey.from_private_bytes(priv)
    partagee = _derive_shared(sk.exchange(X25519PublicKey.from_public_bytes(epk)))
    return AESGCM(partagee).decrypt(nonce, ct, _SEAL_AAD)


def wrap_key(kek: bytes, dek: bytes) -> tuple[bytes, bytes]:
    """Enveloppe une DEK sous une KEK. Retourne (nonce, wrapped)."""
    n = gen_nonce()
    return n, AESGCM(kek).encrypt(n, dek, _WRAP_AAD)


def unwrap_key(kek: bytes, nonce: bytes, wrapped: bytes) -> bytes:
    """Deballe une DEK. Leve `InvalidTag` si la KEK est fausse ou le blob falsifie."""
    return AESGCM(kek).decrypt(nonce, wrapped, _WRAP_AAD)
