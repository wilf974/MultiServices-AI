"""Revue LLM de curation (CLI, LECTURE SEULE).

Lit le journal synchronise, calcule le rapport de curation DETERMINISTE (`curator`), puis passe
les quasi-doublons / contradictions au **comparateur LLM local** (`comparator`) pour dé-bruiter et
proposer des consolidations. Ecrit `logs/curation/curation-llm-YYYYMMDD.md`. **N'ECRIT RIEN en
memoire** : propositions `pending_human` (les commandes `--closes` sont dans le rapport).

CLI : `python -m multiservice.curation_llm [--journal ...] [--out ...]`.
Modele = choix utilisateur (`config.OLLAMA_MODEL`), jamais fige ; temperature 0 (reproductible).
Backend injectable (tests).
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Tuple

from . import comparator, config, curator
from .journal import read_events

_DEF_OUT = str(Path(__file__).resolve().parent.parent / "logs" / "curation")


def _default_backend():
    from .backends import OllamaBackend
    return OllamaBackend(model=config.OLLAMA_MODEL, host=config.OLLAMA_HOST,
                         timeout=config.OLLAMA_TIMEOUT, options={"temperature": 0})


def run(journal_path: str, out_dir: str, backend=None,
        now: Optional[datetime] = None) -> Tuple[str, bool, dict]:
    """Genere la revue LLM datee. Retourne (chemin, needs_attention, result).
    LECTURE SEULE sur la memoire (aucun append). Backend injecte pour les tests."""
    now = now or datetime.now(timezone.utc)
    backend = backend or _default_backend()
    report = curator.curation_report(read_events(journal_path), now=now)
    result = comparator.review_candidates(report, backend)
    md = comparator.format_llm_review_markdown(result)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"curation-llm-{now.strftime('%Y%m%d')}.md"
    path.write_text(md, encoding="utf-8")
    return str(path), comparator.needs_attention(result), result


def main() -> None:
    import argparse
    p = argparse.ArgumentParser(description="Revue LLM locale de curation (lecture seule).")
    p.add_argument("--journal", default=config.JOURNAL_PATH)
    p.add_argument("--out", default=_DEF_OUT)
    a = p.parse_args()
    path, needs, r = run(a.journal, a.out)
    tag = "ACTION" if needs else "ok"                    # sortie ASCII (regle console)
    print(f"[{tag}] revue LLM -> {path} | consolidations={len(r['consolidations'])} "
          f"contradictions={len(r['contradictions'])} ecartes={len(r['dismissed'])} "
          f"incertains={len(r['uncertain'])} (modele {r['model']})")


if __name__ == "__main__":
    main()
