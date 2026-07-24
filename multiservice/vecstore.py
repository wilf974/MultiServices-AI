"""Store vectoriel BINAIRE (index derive, reconstructible) — compact et lu par tranches.

Pourquoi : mesure du 24/07/2026 sur le corpus reel, 2523 vecteurs MiniLM 384d pesaient **21 Mo**
en JSONL — 8504 octets par vecteur la ou float32 en demande 1536 (`0.023847661` en onze caracteres
quand quatre octets suffisent). Et le relire coutait 0,79 s a chaque appel avant mise en cache.

Deux proprietes :
  1. VOLUME : ~1536 o/vecteur en 384d, en-tete negligeable.
  2. RAM : `vectors_for(ids)` lit CE qu'on demande. On ne charge pas tout le corpus en float32
     pour comparer 80 candidats — les bits packes (48 o/vecteur) suffisent au prefiltre.

Ce fichier est un INDEX : jetable, reconstructible (`python -m multiservice.index --onnx`).
Le journal-verite, lui, reste du JSONL append-only et auditable. On n'optimise jamais la verite.

Format : `MSIAVEC1` | dim u32 | count u32 | len(ids) u32 | ids JSON | count*dim float32 (little-endian).
"""
from __future__ import annotations

import json
import struct
from pathlib import Path
from typing import Dict, Iterable, List, Optional

MAGIC = b"MSIAVEC1"
_EN_TETE = len(MAGIC) + 4 * 3          # magic + dim + count + longueur du bloc d'ids


class BinaryVectorStore:
    """Lecture par tranches d'un index binaire. Un fichier absent = index vide (repli lexical)."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._meta = None               # (dim, count, offset_vecs, ids)
        self._pos: Optional[Dict[str, int]] = None

    # --- ecriture ---
    @staticmethod
    def write(path: str | Path, vecs: Dict[str, List[float]]) -> int:
        """Ecrit l'index (remplacement ATOMIQUE : un index tronque ne doit jamais etre servi)."""
        path = Path(path)
        ids = list(vecs.keys())
        dim = len(next(iter(vecs.values()))) if ids else 0
        bloc = json.dumps(ids, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        tmp = path.with_suffix(path.suffix + ".tmp")
        path.parent.mkdir(parents=True, exist_ok=True)
        with tmp.open("wb") as f:
            f.write(MAGIC)
            f.write(struct.pack("<III", dim, len(ids), len(bloc)))
            f.write(bloc)
            for i in ids:
                v = vecs[i]
                if len(v) != dim:
                    raise ValueError("dimension heterogene : %s a %d, attendu %d" % (i, len(v), dim))
                f.write(struct.pack("<%df" % dim, *v))
        tmp.replace(path)
        return len(ids)

    # --- lecture ---
    def _charge_meta(self):
        if self._meta is not None:
            return self._meta
        if not self.path.exists():
            self._meta = (0, 0, _EN_TETE, [])
            return self._meta
        with self.path.open("rb") as f:
            if f.read(len(MAGIC)) != MAGIC:
                raise ValueError("index vectoriel inconnu (magic absent) : %s" % self.path)
            dim, count, n = struct.unpack("<III", f.read(12))
            ids = json.loads(f.read(n).decode("utf-8"))
        self._meta = (dim, count, _EN_TETE + n, ids)
        self._pos = {i: k for k, i in enumerate(ids)}
        return self._meta

    def ids(self) -> List[str]:
        return list(self._charge_meta()[3])

    @property
    def dim(self) -> int:
        return self._charge_meta()[0]

    def vectors_for(self, ids: Iterable[str]) -> Dict[str, List[float]]:
        """Vecteurs des SEULS ids demandes (lecture ciblee). Un id inconnu est ignore."""
        dim, _, offset, _ = self._charge_meta()
        if not dim:
            return {}
        out: Dict[str, List[float]] = {}
        taille = dim * 4
        with self.path.open("rb") as f:
            for i in ids:
                k = (self._pos or {}).get(i)
                if k is None:
                    continue
                f.seek(offset + k * taille)
                out[i] = list(struct.unpack("<%df" % dim, f.read(taille)))
        return out

    def load(self) -> Dict[str, List[float]]:
        """Tout l'index (compat `EmbeddingStore`). A EVITER sur gros corpus : prefiliter puis
        `vectors_for` garde la RAM proportionnelle aux candidats, pas au corpus."""
        dim, count, offset, ids = self._charge_meta()
        if not dim or not count:
            return {}
        taille = dim * 4
        with self.path.open("rb") as f:
            f.seek(offset)
            brut = f.read(count * taille)
        return {i: list(struct.unpack_from("<%df" % dim, brut, k * taille))
                for k, i in enumerate(ids)}

    def bits(self) -> Dict[str, bytes]:
        """Empreintes binaires (1 bit/dimension) pour le PREFILTRE Hamming : 48 o/vecteur en 384d,
        soit ~32x moins que les float32. C'est CE qui a vocation a rester en memoire."""
        from .semantic import pack_bits
        return {i: pack_bits(v) for i, v in self.load().items()}

    def contains(self, event_id: str) -> bool:
        self._charge_meta()
        return event_id in (self._pos or {})


def chemin_binaire(path_jsonl: str | Path) -> Path:
    """Chemin de l'index binaire associe a un index jsonl (meme dossier, suffixe `.vec`)."""
    p = Path(path_jsonl)
    return p if p.suffix == ".vec" else p.with_suffix(".vec")


def migrer_depuis_jsonl(src: str | Path, dest: Optional[str | Path] = None) -> int:
    """Convertit un index jsonl en binaire. L'ancien fichier est LAISSE en place : un index se
    reconstruit, mais on ne supprime pas ce qu'on n'a pas encore verifie."""
    from .semantic import EmbeddingStore
    dest = Path(dest) if dest else chemin_binaire(src)
    return BinaryVectorStore.write(dest, EmbeddingStore(src).load())


def open_store(path: str | Path):
    """Store a servir pour `path` : le BINAIRE s'il existe (compact, lecture ciblee), sinon le
    jsonl. Permet de basculer sans toucher a la configuration ni aux appelants."""
    from .semantic import EmbeddingStore
    p = Path(path)
    if p.suffix == ".vec":
        return BinaryVectorStore(p)
    binaire = chemin_binaire(p)
    return BinaryVectorStore(binaire) if binaire.exists() else EmbeddingStore(p)
