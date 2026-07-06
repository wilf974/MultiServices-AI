# Spec — Comparateur LLM local pour la curation (dé-bruitage + consolidation)

Date : 2026-07-06 · Statut : validé (brainstorming) · Prochain : TDD

## But

Ajouter une couche de **jugement** à la curation, aujourd'hui purement déterministe (Jaccard
lexical) et donc bruitée. Un **LLM local** (Ollama) compare des paires de faits candidats pour :

1. **dé-bruiter** les quasi-doublons et contradictions (écarter les faux positifs : variantes
   FineTune, étapes surstock distinctes…) ;
2. **consolider** les re-logs *reformulés* (le cas « re-log enrichi » que la dédup exacte à
   l'ingest ne peut pas voir) en gardant un canonique et clôturant les variantes.

C'est le pas nommé « le déterministe d'abord, le LLM (comparateur de paires) ensuite » de la spec
curation du 02/07.

## Décisions (brainstorming 06/07)

- **Périmètre** : dé-bruitage **+** consolidation.
- **Consolidation** : le LLM **choisit** lequel des faits **existants** garder (le plus riche) et
  propose de clore les autres (C3). Il **propose, il n'écrit rien de neuf** (pas de synthèse de
  texte) — on reste dans « la mémoire observe ». Extension de `close_duplicate`.
- **Intégration** : **CLI séparée** (`multiservice.curation_llm`). Le rapport déterministe quotidien
  reste rapide et indépendant d'Ollama ; le pass LLM est une revue fine à la demande / planifiable.
- **Approche verdict** : **prompt JSON structuré** (marche avec tout modèle Ollama ; parsing
  défensif) — pas de function-calling (fragile sur petits modèles locaux).
- **Départage** : si `relation=equivalent` mais `keep` ambigu/absent → défaut **garder le plus
  ancien** (déterministe).

## Garanties constitutionnelles (non négociables)

- **LLM local uniquement** (Ollama) : le journal souverain ne part jamais au cloud.
- Le comparateur **n'écrit RIEN en mémoire** : il produit des **propositions** `pending_human` ;
  l'humain colle les commandes `--closes` (comme Phase 2, C1).
- Le LLM **juge** des faits existants et **choisit parmi eux** — il n'**autorise** aucun texte.
- Chaque verdict **cite ses preuves** (ids, textes, sessions) ; **aucun verdict opaque** ; les
  faux positifs écartés sont **listés** (pas de drop silencieux — principe « no silent caps »).
- Modèle = **choix utilisateur** (`config.OLLAMA_MODEL`), jamais figé.

## Architecture

### Cœur pur (testable avec `FakeBackend`)

- `judge_pair(backend, a_text, b_text, kind) -> Verdict`
  - Construit un prompt de comparaison, appelle `backend.chat(...)`, parse le JSON.
  - `Verdict = {relation: "equivalent"|"different"|"contradictory", keep: "a"|"b"|None, rationale: str}`.
  - `keep` n'a de sens que pour `equivalent`. Parsing illisible / relation inconnue →
    `relation="uncertain"` (route vers revue humaine, jamais de proposition automatique).
  - L'appel réseau est **isolé dans le backend** ; `judge_pair` est pur vis-à-vis d'un backend injecté.

- `review_candidates(report, backend, now) -> ReviewResult`
  - Parcourt `report["near_duplicates"]` et `report["contradiction_candidates"]` (paires
    `events=[brief_a, brief_b]`, chaque brief porte `id`/`text`).
  - Pour chaque paire, `judge_pair` :
    - **equivalent** → **consolidation** : `keep_id` = brief choisi (défaut plus ancien), `close_ids`
      = l'autre. Proposition avec `command` (`--closes`, `kind=correction`, session
      `curation-closures`) + `command_reject` (`--rejects`), `status=pending_human`.
    - **contradictory** → **contradiction confirmée** (l'humain résout ; on ne tranche pas).
    - **different** → **écarté** (faux positif, listé avec sa raison).
    - **uncertain** → **revue humaine** (listé, pas de proposition).
  - `ReviewResult = {consolidations, contradictions, dismissed, uncertain, model}`.

### Enveloppe I/O

- Module `multiservice/curation_llm.py` (CLI) :
  - lit le journal synchronisé (`config.JOURNAL_PATH`), calcule `curator.curation_report()`
    (déterministe), instancie le backend Ollama (`config.OLLAMA_MODEL`), appelle `review_candidates`,
    écrit `logs/curation/curation-llm-YYYYMMDD.md` (via un formatteur pur), imprime un résumé ASCII
    `[ACTION|ok] consolidations=.. contradictions=.. ecartes=.. incertains=..`.
  - **Lecture seule** sur la mémoire (aucun append).
- `format_llm_review_markdown(result) -> str` (pur) : consolidations (commande prête à coller),
  contradictions confirmées (à résoudre par l'humain), écartés + incertains (transparence).

## Flux de données

```
journal synchronisé
   -> curator.curation_report()            (déterministe, rapide)
        near_duplicates / contradictions    (paires + preuves)
   -> review_candidates(report, backend)    (LLM local, par paire)
        judge_pair -> {equivalent|different|contradictory|uncertain}
   -> ReviewResult
   -> format_llm_review_markdown -> logs/curation/curation-llm-YYYYMMDD.md
   -> (humain lit, colle les --closes des consolidations qu'il approuve)
```

## Tests (TDD, `FakeBackend` à verdicts canned)

- `judge_pair` : le prompt part au backend ; parse `equivalent`+`keep` / `different` /
  `contradictory` ; JSON illisible → `uncertain` (pas de crash, pas de proposition).
- `review_candidates` :
  - paire equivalent → 1 consolidation, `keep_id`/`close_ids` corrects, commande `--closes`
    présente, `status=pending_human` ; défaut « plus ancien » si `keep` absent.
  - paire different → écartée (dismissed), rien de proposé.
  - paire contradictory → contradiction confirmée.
  - JSON illisible → uncertain (revue humaine).
- `format_llm_review_markdown` : consolidation expose `memlog-http … --closes` ; revue vide →
  « rien ».
- **Aucune mutation** du journal (lecture seule) — vérifié comme `test_curation_report`.

## Hors périmètre (évolutions ultérieures)

- Synthèse d'un texte canonique fusionné (le LLM **écrirait** du contenu) — tension constitutionnelle,
  reporté.
- Pré-filtre par embeddings (bge-m3) pour réduire les appels LLM — optimisation.
- Autonomie (auto-application) — reste `pending_human`.
- Résolution automatique des contradictions — l'humain tranche.
