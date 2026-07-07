"""Chiffrement d'un event + lecture (dechiffrer ou tombstone). S'appuie sur crypto/envelope/keyring.

encrypt_event  : contenu -> DEK aleatoire -> ct dans data.enc ; DEK wrappee sous KEK_slot (hors-ligne).
decrypt_or_tombstone : cles presentes -> clair ; cle detruite (shred) -> tombstone [efface] ; cles
presentes mais tag KO -> IntegrityError (ATTAQUE, pas effacement).
"""
from __future__ import annotations

from . import crypto, envelope
from .events import AetherEvent
from .keystore import KeyMissing


class IntegrityError(Exception):
    """Cles presentes mais authentification KO (AAD/ct falsifie) -> falsification, pas un effacement."""


def encrypt_event(e: AetherEvent, slot_id: str, km) -> AetherEvent:
    """Retourne une copie chiffree de `e` (contenu dans data.enc) et persiste le wrapped_dek dans le keyring."""
    dek = crypto.gen_key()
    nonce = crypto.gen_nonce()
    ct = crypto.aead_encrypt(dek, nonce, envelope.canonical_plaintext(e), envelope.canonical_aad(e))
    kek = km.get_or_create_slot(slot_id)
    wn, wrapped = crypto.wrap_key(kek, dek)
    km.put_dek(e.id, slot_id, wn, wrapped)
    return e.model_copy(update=envelope.build_line_fields(e, slot_id, nonce, ct))


def _tombstone(e: AetherEvent) -> AetherEvent:
    """Fait efface (cle detruite) : contenu remplace par [efface], en-tete (id/type/source/valid_*) conserve."""
    slot = e.data["enc"]["slot"]
    return e.model_copy(update={"title": "[efface]",
                                "description": f"[efface RGPD - slot:{slot}]",
                                "data": {"erased": True, "slot": slot}})


def decrypt_or_tombstone(e: AetherEvent, km) -> AetherEvent:
    """Branche dans read_events (quand un keyring est fourni). Event non chiffre -> rendu tel quel."""
    if not envelope.is_encrypted(e):
        return e
    enc = e.data["enc"]
    try:
        kek = km.get_slot(enc["slot"])                    # KeyMissing si slot shredde (effacement gros)
        wn, wrapped = km.get_dek(e.id)                     # KeyMissing si dek shreddee (effacement fin)
        dek = crypto.unwrap_key(kek, wn, wrapped)
        pt = crypto.aead_decrypt(dek, envelope._ub64(enc["nonce"]), envelope._ub64(enc["ct"]),
                                 envelope.canonical_aad(e))
        return envelope.merge_plaintext(e, pt)
    except KeyMissing:
        return _tombstone(e)                              # effacement LEGITIME
    except crypto.InvalidTag as ex:
        raise IntegrityError(f"AAD/ct falsifie sur {e.id}") from ex   # cles presentes mais tag KO = ATTAQUE
