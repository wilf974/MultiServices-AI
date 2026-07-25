"""V5 — MANIFESTE D'USAGE : rendre n'importe quelle IA immediatement competente.

La surface est deja ouverte (outils MCP, API web). Ce qui manquait, c'est un document que l'agent
lit EN PREMIER : comment lire, comment ecrire, quoi ne jamais ecrire, et quelles regles s'imposent
a lui. Cela vivait dans `CLAUDE.md` — specifique a un seul agent, invisible pour ChatGPT ou Ollama.

DEUX exigences, apprises a nos depens le 25/07/2026 :

1. **DERIVE, jamais recopie.** Les kinds, verdicts et relations sont lus depuis le code. Un
   manifeste redige a la main ment des la premiere evolution — comme les listes de types devinees
   qui ont fait passer des tests pour de mauvaises raisons.
2. **Il ne ment pas sur l'etat.** `health` affichait « available » pendant que le canal semantique
   etait mort. Un manifeste qui promet le semantique avec un index vide envoie l'agent dans le mur.

Texte PUR, lisible par n'importe quel LLM quel que soit son harnais.
"""
from __future__ import annotations

from typing import Any, Dict, Optional


def rendre(sante: Optional[Dict[str, Any]] = None) -> str:
    """Mode d'emploi de cette memoire, derive du code. PUR."""
    from . import projlog
    from .memory import RELATIONS, VERDICTS

    kinds = ", ".join(sorted(projlog.KINDS))
    verdicts = " | ".join(VERDICTS)
    relations = " | ".join(RELATIONS)

    bloc_etat = ""
    if sante and sante.get("degraded") and sante.get("warnings"):
        lignes = "\n".join("  - %s" % w for w in sante["warnings"])
        bloc_etat = ("\nETAT ACTUEL — capacites DEGRADEES, n'attendez pas d'elles ce qu'elles ne\n"
                     "peuvent pas donner :\n%s\n" % lignes)

    return f"""MEMOIRE MULTISERVICE — MODE D'EMPLOI POUR UN AGENT

Ce que c'est : un journal append-only, date et source, ou plusieurs IA et un humain deposent ce
qu'ils apprennent. Il n'ecrase jamais : il corrige en ajoutant. Vous pouvez donc lui faire
confiance sur ce qui a ete dit, quand, et par qui.
{bloc_etat}
COMMENCEZ PAR CECI
  resume(projet)   -> en UN appel : les pieges actifs, la sante du substrat, l'etat du projet,
                      ce qui a bouge, ce qui a change d'avis, ce qui attend un arbitrage.
                      C'est la premiere chose a lire. Le reste ne sert qu'ensuite.

POUR CHERCHER
  recall / recall_semantic (par le sens) · brief (un sujet) · recent (quoi de neuf)
  why / replay / replay_event (pourquoi l'agent a vu ca) · as_of (ce qui etait vrai a T)
  pitfalls  -> ce qui a deja coute une erreur. A lire avant d'agir, pas apres.
  Les textes sont bornes par defaut : passez chars=0 pour l'integralite.

POUR ECRIRE (jamais via la surface de lecture : elle est en LECTURE SEULE)
  memlog-http "<le fait, une phrase>" --kind <{kinds}> --session <sujet-stable>
  Champs structures, a cote du texte et jamais a sa place :
    --pourquoi   la raison        --piege     le garde-fou revele
    --commande   la commande      --ref       commit / fichier / id (repetable)
  Ecrivez le FAIT dans le texte et le reste dans les champs : un futur lecteur scanne les faits,
  puis descend dans le detail. Un pave de 2000 caracteres devra etre re-parse par quelqu'un.

POUR REPONDRE A UN AUTRE AGENT (c'est ce qui fait la difference)
  --confirme / --contredit / --precise <id>     ({relations})
  Ce qui compte n'est pas le nombre de confirmations mais la DIVERSITE des sources : vous ne
  pouvez pas vous confirmer vous-meme, et c'est voulu.
  Contredire ne perime rien : cela remonte comme « a trancher ». L'humain arbitre.

POUR DIRE CE QUI VOUS A SERVI
  --utile / --inutile / --a-evite-erreur <id>   (verdicts : {verdicts})
  Sans ce signal, la curation devine ce qu'il faut perimer. Un souvenir qui a evite une erreur
  est protege — encore faut-il le dire.

CE QU'IL NE FAUT JAMAIS ECRIRE
  - un SECRET (cle, jeton, mot de passe) : le journal est append-only, on ne l'efface pas ;
  - un GABARIT non rempli (« <sujet> ») : la garde le refuse, et c'est tant mieux ;
  - ce que le depot dit deja mieux (le code, la doc longue). Ecrivez ce qui n'a pas d'autre
    foyer : les raisons, les impasses, les pieges.

LES TROIS REGLES QUI S'IMPOSENT A VOUS
  C1  L'humain tranche. Vous observez, vous proposez ; vous ne decidez pas a sa place.
  C2  Votre source est IMPOSEE par votre identite, pas declaree. Vous ne pouvez pas parler
      au nom d'un autre agent.
  C3  On ne supprime jamais. Corriger, c'est ajouter une correction qui clot l'ancien fait —
      l'historique reste lisible, et le « pourquoi ca a change » avec lui.
"""


def main() -> int:
    import argparse
    p = argparse.ArgumentParser(description="Manifeste d'usage de la memoire (lecture seule).")
    p.add_argument("--sante", action="store_true",
                   help="inclut l'etat degrade reel (index, fraicheur)")
    a = p.parse_args()
    sante = None
    if a.sante:
        try:
            from . import config, memory
            from .journal import read_events
            from .semantic import EmbeddingStore
            evs = read_events(config.JOURNAL_PATH)
            idx = memory.index_coverage(evs, EmbeddingStore(config.EMBED_PATH).load())
            sante = memory.health(evs, index=idx)
        except Exception:
            sante = None                              # le mode d'emploi vaut meme sans diagnostic
    print(rendre(sante=sante))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
