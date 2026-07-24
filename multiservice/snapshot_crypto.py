"""Enveloppe chiffree au niveau FICHIER — pour les snapshots `.bak-*` du journal.

Pourquoi : `sync_memory_merge.ps1` copie le journal entier avant chaque fusion, des DEUX cotes
(poste + central). Ces copies portent tout le contenu sensible sans aucune des gardes du journal.

Meme hierarchie de cles que le chiffrement au repos (design ⑦, `docs/ENCRYPTION-AT-REST.md`) :
DEK tiree par fichier -> chiffre le contenu ; DEK wrappee sous la KEK d'un slot -> stockee dans
l'en-tete ; la KEK vit HORS du fichier (keyring). Detruire la KEK du slot rend tous ses snapshots
illisibles sans les reecrire (crypto-shred).

Format : `<en-tete JSON sur UNE ligne>\\n<ciphertext binaire>`. L'en-tete est CLAIR (on doit pouvoir
inventorier des snapshots sans pouvoir les lire) mais AUTHENTIFIE : il sert d'AAD, donc le falsifier
fait echouer le dechiffrement.

PUR (hors tirage aleatoire) : bytes -> bytes. Les I/O sont dans `encrypt_snapshots.py`.
"""
from __future__ import annotations

import base64
import hashlib
import json
from typing import Optional

from . import crypto

VERSION = 1
_b64 = lambda b: base64.b64encode(b).decode()
_ub64 = lambda s: base64.b64decode(s)


def _aad(header: dict) -> bytes:
    """AAD = l'en-tete SANS la DEK wrappee, canonique. Lie le ciphertext a son identite declaree
    (nom d'origine, taille, empreinte du clair)."""
    hdr = {k: v for k, v in header.items() if k != "dek"}
    return json.dumps(hdr, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def seal(clair: bytes, kek: bytes, slot_id: str, meta: Optional[dict] = None) -> bytes:
    """Chiffre `clair` sous une DEK neuve, elle-meme wrappee sous `kek`. Retourne le blob complet."""
    dek = crypto.gen_key()
    nonce = crypto.gen_nonce()
    dek_nonce, dek_ct = crypto.wrap_key(kek, dek)
    header = {
        "v": VERSION,
        "alg": "AESGCM",
        "slot": slot_id,
        "nonce": _b64(nonce),
        "taille_clair": len(clair),
        "sha256_clair": hashlib.sha256(clair).hexdigest(),   # verifiable APRES dechiffrement
        "meta": meta or {},
        "dek": {"nonce": _b64(dek_nonce), "ct": _b64(dek_ct)},
    }
    ct = crypto.aead_encrypt(dek, nonce, clair, _aad(header))
    return json.dumps(header, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8") + b"\n" + ct


def read_header(blob: bytes) -> dict:
    """En-tete d'un blob, SANS la cle : inventorier n'est pas lire. PUR."""
    ligne, _, _ = blob.partition(b"\n")
    return json.loads(ligne.decode("utf-8"))


def unseal(blob: bytes, kek: bytes) -> bytes:
    """Dechiffre un blob. Leve `crypto.InvalidTag` si la KEK est fausse, ou si l'en-tete ou le
    ciphertext a ete falsifie. Verifie l'empreinte du clair (corruption silencieuse)."""
    ligne, sep, ct = blob.partition(b"\n")
    if not sep:
        raise ValueError("blob de snapshot malforme : en-tete absent")
    header = json.loads(ligne.decode("utf-8"))
    dek = crypto.unwrap_key(kek, _ub64(header["dek"]["nonce"]), _ub64(header["dek"]["ct"]))
    clair = crypto.aead_decrypt(dek, _ub64(header["nonce"]), ct, _aad(header))
    attendu = header.get("sha256_clair")
    if attendu and hashlib.sha256(clair).hexdigest() != attendu:
        raise ValueError("empreinte du clair incoherente : snapshot corrompu")
    return clair
