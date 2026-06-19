"""DEMO concrete : la MEME question, SANS memoire puis AVEC MultiService IA.

But : montrer ce que la memoire apporte a un agent, sur des donnees 100 % fictives (DunkBot).
Le clou : la 1re decision (NEMA-17) a ete CORRIGEE plus tard (servo). Sans memoire, un agent
peut re-recommander le moteur PERIME ; avec la memoire + le drapeau C3, il sert la verite courante.

Aucun modele requis : on demontre la couche MEMOIRE (deterministe, tourne partout).
Lancer :  python examples/memory_demo/compare.py
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))  # racine du depot
sys.path.insert(0, os.path.dirname(__file__))

from multiservice import memory          # noqa: E402
from seed_demo import build_events, QUERY  # noqa: E402

LINE = "-" * 70


def _first_line(text: str, n: int = 88) -> str:
    s = " ".join(text.split())
    return s if len(s) <= n else s[:n] + "..."


def without_memory(query: str) -> None:
    print(LINE)
    print("SANS MultiService IA  (agent sans memoire)")
    print(LINE)
    print(f"  Q: {query}")
    print("  Contexte disponible : (aucun)")
    print("  -> Reponse a l'aveugle. Au mieux des generalites ; au pire, il re-propose")
    print("     la 1re idee venue (le NEMA-17) sans savoir qu'elle a ete abandonnee.")
    print()


def with_memory(query: str, events: list) -> None:
    print(LINE)
    print("AVEC MultiService IA  (memoire locale, lecture seule)")
    print(LINE)

    brief = memory.topic_brief(events, query, k=5)
    code = memory.recall(events, query, has_code=True, k=2)
    table = memory.recall(events, query, has_table=True, k=2)
    cov = memory.index_coverage(events, {})   # pas d'index dans la demo -> montre 0% (honnete)

    # decisions, avec drapeau de fraicheur C3
    print("  brief() — un seul appel :")
    for d in brief["decisions"]:
        flag = "  [PERIME C3 !]" if d["superseded"] else ""
        print(f"    DECISION{flag} : {_first_line(d['text'])}")
    revised = [r for r in brief["revised"]]
    if revised:
        print("    -> revise depuis (corrected_by) : la decision ci-dessus n'est PLUS la verite.")

    # la verite courante = la correction la plus recente pertinente
    corrections = [m for m in brief["memories"] if m["type"] == "correction"]
    if corrections:
        print(f"  VERITE COURANTE (correction) : {_first_line(corrections[0]['text'])}")

    if code:
        print(f"  Code retrouve (has_code)     : {_first_line(code[0]['text'])}")
    if table:
        print(f"  Nomenclature (has_table)     : {_first_line(table[0]['text'])}")

    print(f"  Provenance : 100 % des hits sources ; fraicheur index : {cov['covered_pct']}% "
          f"(demo sans index -> sait que le semantique serait partiel)")
    print()
    print("  ==> L'agent repond : « servo MG996R (le NEMA-17 a ete corrige : il calait) »,")
    print("      avec le code de flip et la nomenclature, le tout source et date.")
    print()


def main() -> None:
    events = build_events()
    print()
    print("######  DEMO MultiService IA — projet fictif DunkBot 3000  ######")
    print(f"Question posee : {QUERY}\n")
    without_memory(QUERY)
    with_memory(QUERY, events)
    print(LINE)
    print("MORALE : sans memoire, l'agent risque de re-recommander le moteur PERIME.")
    print("Avec MultiService IA, la 1re decision est marquee perimee (C3), la verite")
    print("courante est servie, sourcee et datee — une force, pas une dependance.")
    print(LINE)


if __name__ == "__main__":
    main()
