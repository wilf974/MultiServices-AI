"""Client d'ecriture distante : signe et POST un evenement vers le serveur de memoire central.
Config par env : MEM_INGEST_URL, MEM_CLIENT_CERT, MEM_CLIENT_KEY, MEM_HMAC_KEY.
Le serveur impose la source via le CN du certificat ; le client ne la fixe pas."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

from .hygiene import looks_like_placeholder
from .policy import contains_secret


def build_request(text: str, kind: str, session: str, hmac_key: str,
                  now: Optional[datetime] = None, force: bool = False,
                  data: Optional[dict] = None) -> Tuple[bytes, str]:
    """Construit (corps JSON, signature HMAC hex). Nonce aleatoire, ts ISO8601 UTC.
    `force=True` ajoute force au corps signe (le serveur laisse alors passer un texte
    ressemblant a un gabarit) ; absent sinon (corps inchange pour les clients existants).
    `data` (dict) voyage SIGNE dans le corps — ex curation Phase 2 : {"closes": [ids]}
    (cloture ciblee) ou {"rejects": [ids]} (proposition rejetee)."""
    ts = (now or datetime.now(timezone.utc)).isoformat()
    payload = {"text": text, "kind": kind, "session": session, "ts": ts, "nonce": uuid.uuid4().hex}
    if force:
        payload["force"] = True
    if data:
        payload["data"] = data
    body = json.dumps(payload).encode("utf-8")
    sig = hmac.new(hmac_key.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return body, sig


def main() -> None:
    p = argparse.ArgumentParser(description="Ecriture distante vers la memoire centrale (ingest mTLS).")
    p.add_argument("text")
    p.add_argument("--kind", default="decision")
    p.add_argument("--session", default="ingest")
    p.add_argument("--force", action="store_true",
                   help="journalise MEME si le texte ressemble a un gabarit non rempli")
    p.add_argument("--closes", default="",
                   help="curation approuvee : ids a CLORE precisement (virgules) ; "
                        "exige --kind correction, session neutre recommandee (curation-closures)")
    p.add_argument("--rejects", default="",
                   help="proposition de curation REJETEE : ids cibles (virgules)")
    a = p.parse_args()

    # Garde anti-gabarit (pollution observee au journal). Refus AVANT le reseau ; l'humain
    # peut passer outre en connaissance de cause (--force, esprit C1).
    if not a.force and looks_like_placeholder(a.text):
        print("[memlog-http] REFUS : texte de gabarit non rempli (--force pour passer outre)")
        raise SystemExit(2)
    # Garde anti-secret : ne JAMAIS envoyer une valeur de cle/jeton au journal (ineffacable).
    if not a.force and contains_secret(a.text):
        print("[memlog-http] REFUS : secret detecte (cle/jeton ; --force pour passer outre)")
        raise SystemExit(2)

    data = {}
    closes = [x.strip() for x in a.closes.split(",") if x.strip()]
    rejects = [x.strip() for x in a.rejects.split(",") if x.strip()]
    if closes:
        data["closes"] = closes                      # cloture CIBLEE (lue par _closes_index)
    if rejects:
        data["rejects"] = rejects                    # le journal EST la file (plus de pending)
    if closes and a.kind != "correction":
        print("[memlog-http] REFUS : --closes exige --kind correction (cloture C3)")
        raise SystemExit(2)

    import ssl
    import httpx
    url = os.environ["MEM_INGEST_URL"]
    body, sig = build_request(a.text, a.kind, a.session, os.environ["MEM_HMAC_KEY"],
                              force=a.force, data=(data or None))
    # mTLS : le cert client est porte par un SSLContext (httpx >= 0.28 a retire l'argument cert
    # des fonctions de haut niveau ; verify=ctx reste valable sur toutes les versions recentes).
    ctx = ssl.create_default_context()
    ctx.load_cert_chain(certfile=os.environ["MEM_CLIENT_CERT"], keyfile=os.environ["MEM_CLIENT_KEY"])
    with httpx.Client(verify=ctx, timeout=15) as client:
        r = client.post(url, content=body,
                        headers={"X-Mem-Signature": sig, "Content-Type": "application/json"})
    print(r.status_code, r.text)


if __name__ == "__main__":
    main()
