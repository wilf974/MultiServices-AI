"""O1b - Sauvegarde locale du substrat (assurance contre la perte du poste/SPOF).

Couvre journaux (*.jsonl) + dossier skills/ vers un SECOND support LOCAL (cle/disque USB).
  - APPEND-SAFE : on copie, on n'efface JAMAIS la destination (rien ne disparait).
  - MANIFESTE SHA-256 : chaque sauvegarde ecrit un manifeste ; `verify()` recalcule et
    compare (une sauvegarde non verifiee n'est pas une sauvegarde).
  - Garde honnete : un meme disque ne survit pas a une panne disque -> avertir si la
    destination est sur le meme lecteur que la source.

Logique testable ; seuls copie/lecture touchent le disque.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Sequence

MANIFEST = "backup-manifest.json"


def _sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _collect(src: Path, patterns: Sequence[str], subdirs: Sequence[str]) -> List[Path]:
    files: List[Path] = []
    for pat in patterns:
        files += [p for p in src.glob(pat) if p.is_file()]
    for d in subdirs:
        base = src / d
        if base.exists():
            files += [p for p in base.rglob("*") if p.is_file()]
    return sorted(set(files))


def backup(src: str | Path, dest: str | Path,
           patterns: Sequence[str] = ("*.jsonl",),
           subdirs: Sequence[str] = ("skills",),
           now: datetime | None = None) -> Dict:
    """Copie le substrat vers dest. APPEND-SAFE. Retourne le manifeste."""
    src, dest = Path(src), Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    now = now or datetime.now(timezone.utc)
    manifest: Dict = {"created": now.isoformat(), "source": str(src), "files": {}}
    for f in _collect(src, patterns, subdirs):
        rel = f.relative_to(src)
        target = dest / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(f, target)                      # jamais d'effacement de l'existant
        manifest["files"][str(rel).replace("\\", "/")] = {
            "sha256": _sha256(f), "bytes": f.stat().st_size,
        }
    (dest / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify(dest: str | Path) -> List[str]:
    """Recalcule les SHA-256 cote destination et compare au manifeste. [] = OK."""
    dest = Path(dest)
    mf = dest / MANIFEST
    if not mf.exists():
        return ["manifeste absent : sauvegarde introuvable"]
    manifest = json.loads(mf.read_text(encoding="utf-8"))
    problems: List[str] = []
    for rel, meta in manifest["files"].items():
        t = dest / rel
        if not t.exists():
            problems.append(f"manquant: {rel}")
        elif _sha256(t) != meta["sha256"]:
            problems.append(f"corrompu: {rel}")
    return problems


def main() -> None:
    import argparse
    from . import config
    p = argparse.ArgumentParser(description="O1b - sauvegarde locale du substrat (verifiable).")
    p.add_argument("--dest", required=True, help="dossier sur le SECOND support (ex: E:\\aethercore-backup)")
    p.add_argument("--source", default=config.AETHER_HOME)
    p.add_argument("--verify", action="store_true", help="verifier une sauvegarde existante")
    a = p.parse_args()

    if a.verify:
        probs = verify(a.dest)
        if probs:
            print(f"[ECHEC] {len(probs)} probleme(s) :")
            for x in probs[:20]:
                print("  -", x)
        else:
            print("[OK] sauvegarde verifiee : tous les fichiers presents et intacts.")
        return

    src_root = Path(a.source).anchor
    dest_root = Path(a.dest).anchor
    if src_root and src_root == dest_root:
        print(f"[AVERTISSEMENT] destination sur le meme lecteur que la source ({dest_root}).")
        print("                Un meme disque ne survit pas a une panne disque. Prends un support PHYSIQUE distinct.")
    m = backup(a.source, a.dest)
    n = len(m["files"])
    total = sum(v["bytes"] for v in m["files"].values())
    print(f"[OK] {n} fichier(s) sauvegarde(s) ({total} octets) -> {a.dest}")
    print(f"     Verifie : python -m multiservice.backup --dest \"{a.dest}\" --verify")


if __name__ == "__main__":
    main()
