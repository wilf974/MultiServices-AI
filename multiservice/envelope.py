"""PUR — l'enveloppe chiffree portee par la ligne du journal (`data.enc`).

Le contenu sensible (`title`, `description`, `data` hors `enc`) est chiffre dans `ct` ; la ligne ne porte
que le ciphertext + un en-tete clair. L'AAD lie le ciphertext a l'identite de l'event.

Garde ⑥ : l'AAD ne contient QUE des chaines `[id, type, source]`. JAMAIS de datetime : un `isoformat()`
recalcule apres re-parse n'est pas byte-stable (microsecondes/fuseau) -> `InvalidTag` sur un event
LEGITIME. `valid_from`/`valid_to` restent proteges par la chaine de hachage (`integrity.py`), pas par l'AAD.
"""
from __future__ import annotations

import base64
import json

from .events import AetherEvent

AAD_FIELDS = ["id", "type", "source"]          # chaines seules — voir garde ⑥

_b64 = lambda b: base64.b64encode(b).decode()
_ub64 = lambda s: base64.b64decode(s)


def canonical_plaintext(e: AetherEvent) -> bytes:
    """JSON canonique du contenu sensible : {title, description, data\\{sans enc\\}}. PUR, deterministe."""
    data = {k: v for k, v in e.data.items() if k != "enc"}
    obj = {"title": e.title, "description": e.description, "data": data}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_aad(e: AetherEvent) -> bytes:
    """AAD = en-tete canonique [id, type, source] — CHAINES SEULES (garde ⑥). PUR, byte-stable."""
    hdr = {"id": e.id, "type": e.type.value, "source": e.source}
    return json.dumps(hdr, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def is_encrypted(e: AetherEvent) -> bool:
    return isinstance(e.data, dict) and "enc" in e.data


def build_line_fields(e: AetherEvent, slot_id: str, nonce: bytes, ct: bytes) -> dict:
    """Champs de la ligne journal apres chiffrement : title/description vides, contenu dans data.enc.
    AUCUN secret ici (la ligne est scellee par la chaine ; les cles vivent hors-journal)."""
    return {"title": "", "description": "",
            "data": {"enc": {"v": 1, "alg": "AESGCM", "slot": slot_id,
                             "nonce": _b64(nonce), "ct": _b64(ct), "aad": AAD_FIELDS}}}


def merge_plaintext(e: AetherEvent, pt: bytes) -> AetherEvent:
    """Refusionne le clair dechiffre dans l'event (title/description/data). PUR (model_copy)."""
    obj = json.loads(pt)
    return e.model_copy(update={"title": obj["title"], "description": obj["description"],
                                "data": obj["data"]})
