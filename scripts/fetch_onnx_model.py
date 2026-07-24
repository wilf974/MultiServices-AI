"""Telecharge le modele d'embedding ONNX local (MiniLM-L6-v2, 384d) dans `config.ONNX_DIR`.

C'est un telechargement de POIDS, une fois, puis tout tourne hors ligne : aucune API d'inference
ni d'embedding hebergee n'est appelee a l'usage (contrainte constitutionnelle (c) preservee).

    python scripts/fetch_onnx_model.py            # -> ~/.aethercore/onnx/all-MiniLM-L6-v2
    python scripts/fetch_onnx_model.py --dest D:\\ailleurs

Sorties console en ASCII (console PowerShell).
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

REPO = "sentence-transformers/all-MiniLM-L6-v2"
FICHIERS = {"onnx/model.onnx": "model.onnx", "tokenizer.json": "tokenizer.json"}


def main() -> int:
    ap = argparse.ArgumentParser(description="Recupere le modele ONNX d'embedding local")
    ap.add_argument("--dest", default=None, help="dossier cible (defaut : config.ONNX_DIR)")
    args = ap.parse_args()

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from multiservice import config
    dest = Path(args.dest or config.ONNX_DIR)
    dest.mkdir(parents=True, exist_ok=True)

    try:
        from huggingface_hub import hf_hub_download
    except ImportError:
        print("ERREUR: huggingface_hub absent. pip install huggingface_hub")
        return 1

    for distant, local in FICHIERS.items():
        cible = dest / local
        if cible.exists():
            print("deja la : %s" % cible)
            continue
        print("telechargement %s ..." % distant)
        chemin = hf_hub_download(repo_id=REPO, filename=distant)
        shutil.copyfile(chemin, cible)
        print("  -> %s (%.1f Mo)" % (cible, cible.stat().st_size / 1e6))

    print("OK. MULTISERVICE_ONNX_DIR=%s" % dest)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
