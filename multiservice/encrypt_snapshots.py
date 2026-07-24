"""Chiffre les SNAPSHOTS `.bak-*` du journal (I/O autour de `snapshot_crypto`).

    python -m multiservice.encrypt_snapshots                 # etat des lieux (dry-run)
    python -m multiservice.encrypt_snapshots --apply         # chiffre, retire le clair
    python -m multiservice.encrypt_snapshots --apply --keep  # chiffre, GARDE le clair
    python -m multiservice.encrypt_snapshots --list          # inventaire (sans dechiffrer)
    python -m multiservice.encrypt_snapshots --decrypt <fichier.enc> [--dest <sortie>]

Le journal-verite n'est JAMAIS touche : ce module ne connait que les snapshots. Chiffrer le
journal lui-meme se fait par `MULTISERVICE_ENCRYPT=1` + `encrypt_migrate` (chiffrement par
EVENEMENT, que les lecteurs savent lire) — ce sont deux mecanismes distincts et complementaires.

Sorties console en ASCII.
"""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path
from typing import Optional

from . import config
from .keyring import KeyManager
from .snapshot_crypto import read_header, seal, seal_public, unseal, unseal_private

SLOT = "snapshots"
MOTIF = "journal-llm.jsonl.bak-*"
SUFFIXE = ".enc"


def _snapshots_clairs(dossier: Path, motif: str = MOTIF):
    """Snapshots encore en clair. Le journal lui-meme ne matche pas le motif (garde par le test)."""
    return sorted(p for p in dossier.glob(motif) if p.suffix != SUFFIXE and p.is_file())


def chiffrer_dossier(dossier: str | Path, km: Optional[KeyManager] = None, *,
                     slot_id: str = SLOT, motif: str = MOTIF,
                     garder_clair: bool = False, pub: Optional[bytes] = None) -> dict:
    """Chiffre chaque snapshot en clair du dossier. IDEMPOTENT : un snapshot deja chiffre
    (fichier .enc present) est laisse tel quel. Retourne un compte-rendu.

    Deux modes :
      - keyring local (defaut) : DEK wrappee sous la KEK d'un slot -> le poste chiffre ET relit.
      - `pub` (cle publique X25519) : pour un noeud qu'on ne controle pas seul (le central). Il
        chiffre sans jamais pouvoir relire ; aucun keyring n'est requis ni souhaitable chez lui."""
    dossier = Path(dossier)
    kek = None
    if pub is None:
        km = km or KeyManager()
        kek = km.get_or_create_slot(slot_id)
    # Compte AVANT : au passage suivant les clairs ont disparu, on ne peut plus les recompter.
    deja = len({p.name for p in dossier.glob(motif + SUFFIXE)})
    r = {"chiffres": 0, "deja_chiffres": deja, "octets": 0, "erreurs": []}
    for src in _snapshots_clairs(dossier, motif):
        dest = src.with_name(src.name + SUFFIXE)
        if dest.exists():
            continue
        try:
            clair = src.read_bytes()
            mtime = src.stat().st_mtime
            meta = {"nom": src.name, "mtime": int(mtime)}
            blob = (seal_public(clair, pub, meta=meta) if pub is not None
                    else seal(clair, kek, slot_id=slot_id, meta=meta))
            tmp = dest.with_suffix(dest.suffix + ".tmp")
            tmp.write_bytes(blob)
            tmp.replace(dest)                       # remplacement atomique : jamais de .enc partiel
            # Le chiffre herite de la DATE du snapshot : la purge par retention filtre sur
            # LastWriteTime ; sans cela un vieux snapshot rajeunirait en etant chiffre.
            os.utime(dest, (mtime, mtime))
            if not garder_clair:
                src.unlink()                        # le clair ne part qu'APRES l'ecriture du chiffre
            r["chiffres"] += 1
            r["octets"] += len(clair)
        except Exception as e:                      # un snapshot fautif ne doit pas bloquer les autres
            r["erreurs"].append(f"{src.name}: {type(e).__name__}: {e}")
    return r


def dechiffrer_fichier(chemin: str | Path, km: Optional[KeyManager] = None,
                       dest: Optional[str | Path] = None,
                       priv: Optional[bytes] = None) -> Path:
    """Restaure un snapshot chiffre. `dest` par defaut = le nom d'origine, sans `.enc`.
    L'en-tete dit quel mode : `pub` -> cle PRIVEE requise ; sinon keyring local."""
    chemin = Path(chemin)
    blob = chemin.read_bytes()
    hdr = read_header(blob)
    if hdr.get("mode") == "pub":
        if priv is None:
            raise ValueError("snapshot scelle vers une cle publique : cle privee requise (--priv)")
        clair = unseal_private(blob, priv)
    else:
        km = km or KeyManager()
        kek = km.get_slot(hdr["slot"])              # KeyMissing si la cle du slot a ete detruite
        clair = unseal(blob, kek)
    sortie = Path(dest) if dest else chemin.with_name(chemin.name[:-len(SUFFIXE)])
    sortie.write_bytes(clair)
    return sortie


def inventaire(dossier: str | Path, motif: str = MOTIF) -> list:
    """Liste les snapshots CHIFFRES sans les dechiffrer : inventorier n'est pas lire."""
    out = []
    for p in sorted(Path(dossier).glob(motif + SUFFIXE)):
        try:
            h = read_header(p.read_bytes()[:4096])  # l'en-tete suffit
            out.append({"fichier": p.name, "slot": h.get("slot"),
                        "taille_clair": h.get("taille_clair"), "nom": h.get("meta", {}).get("nom")})
        except Exception as e:
            out.append({"fichier": p.name, "erreur": f"{type(e).__name__}: {e}"})
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Chiffre les snapshots .bak-* du journal.")
    p.add_argument("--dir", default=str(Path(config.JOURNAL_PATH).parent))
    p.add_argument("--apply", action="store_true", help="applique (sinon : dry-run)")
    p.add_argument("--keep", action="store_true", help="garde aussi le clair")
    p.add_argument("--list", action="store_true", help="inventaire des snapshots chiffres")
    p.add_argument("--decrypt", default=None, metavar="FICHIER.enc")
    p.add_argument("--dest", default=None)
    # Mode NOEUD DISTANT : il chiffre avec la publique, il ne relit jamais.
    p.add_argument("--pubkey", default=None, metavar="FICHIER",
                   help="cle publique X25519 (base64) : chiffre sans pouvoir dechiffrer")
    p.add_argument("--priv", default=None, metavar="FICHIER",
                   help="cle privee X25519 (base64) : pour relire un snapshot scelle")
    p.add_argument("--genkey", default=None, metavar="PREFIXE",
                   help="genere une paire -> PREFIXE.priv / PREFIXE.pub")
    a = p.parse_args()
    dossier = Path(a.dir)

    if a.genkey:
        from . import crypto
        priv, pub = crypto.gen_keypair()
        pp, pubp = Path(a.genkey + ".priv"), Path(a.genkey + ".pub")
        pp.write_text(base64.b64encode(priv).decode(), encoding="utf-8")
        pubp.write_text(base64.b64encode(pub).decode(), encoding="utf-8")
        try:
            os.chmod(pp, 0o600)
        except OSError:
            pass
        print("[snapshots] paire generee : %s (PRIVEE, ne quitte pas ce poste) / %s (publique)"
              % (pp, pubp))
        return 0

    if a.decrypt:
        priv = base64.b64decode(Path(a.priv).read_text().strip()) if a.priv else None
        sortie = dechiffrer_fichier(a.decrypt, dest=a.dest, priv=priv)
        print("[snapshots] restaure -> %s (%d octets)" % (sortie, sortie.stat().st_size))
        return 0

    if a.list:
        for e in inventaire(dossier):
            print("  %s" % e)
        return 0

    if not a.apply:
        clairs = _snapshots_clairs(dossier)
        total = sum(f.stat().st_size for f in clairs)
        print("[snapshots] dry-run : %d en clair (%.1f Mo) dans %s"
              % (len(clairs), total / 1e6, dossier))
        for f in clairs[:5]:
            print("    %s" % f.name)
        if len(clairs) > 5:
            print("    ... et %d autres" % (len(clairs) - 5))
        print("[snapshots] relancer avec --apply pour chiffrer.")
        return 0

    pub = base64.b64decode(Path(a.pubkey).read_text().strip()) if a.pubkey else None
    r = chiffrer_dossier(dossier, garder_clair=a.keep, pub=pub)
    print("[snapshots] %d chiffres (%.1f Mo), %d deja chiffres%s"
          % (r["chiffres"], r["octets"] / 1e6, r["deja_chiffres"],
             " [vers cle publique : ce noeud ne peut pas relire]" if pub else ""))
    for e in r["erreurs"]:
        print("    ERREUR %s" % e)
    return 1 if r["erreurs"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
