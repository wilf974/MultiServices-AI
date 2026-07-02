# Plan d'implémentation — IA de curation de la mémoire (Phase 1)

> Déroulé TDD du cadrage <user> (`docs/curation/PLAN.md`, 02/07/2026), spec :
> `docs/superpowers/specs/2026-07-02-curation-memoire-design.md`.

## Phase 0 — Cadrage — ✅ FAIT (02/07)
- [x] Lever la décision « pas d'intelligence avant signal » : signal atteint (~130 déc./45 corr.
      sur 30 j). **Corrections C3 à journaliser dans les sessions `suite-observation` (d9d7e19c)
      et `observation` (ef345f29)** → `scripts/ingest-curation.ps1` (l'humain signe, C1).
- [x] Modèle : **local Ollama uniquement** (le journal souverain ne part jamais au cloud) ;
      déterministe d'abord, LLM en narration plus tard. Modèle au choix (décision 01/07).

## Phase 1 — Lecture seule — ✅ LIVRÉ (02/07)
- [x] `multiservice/curator.py` : détecteurs purs (doublons exacts/proches, gabarits valides,
      décisions anciennes, contradictions candidates) + `curation_report` borné + `make_proposal`.
- [x] Outil MCP `curation` (lecture seule, D5) dans `mcp_server.py`.
- [x] `tests/test_curator.py` (11 tests, cas réels : correction ×2, `<sujet>` still_standing).
- [ ] Premier rapport sur le journal RÉEL + revue humaine → recalibrer les seuils (BITS).
- [ ] Brancher `curation` dans `memory_tools.py` (agent local) et l'API web (`GET /curation`).

## Phase 2 — Écriture supervisée (après critères §7 de la spec)
- [ ] File d'attente des propositions (approve/reject humain).
- [ ] Exécution des approuvées via ingest (kind=correction, session de l'original → supersede C3).
- [ ] Chaque action de curation journalisée dans la mémoire elle-même (auditable).
- [ ] Narrateur LLM local (prompts §4 de la spec, sortie JSON validée).

## Phase 3 — Autonomie partielle
- [ ] Automatiser UNIQUEMENT `close_duplicate` strict (texte identique + même session).
- [ ] Tout le reste demeure supervisé.

## Échéance socle : 07/07 — livrables couverts par la spec (architecture, rapports, schéma,
## prompts, contrat API, jeu de tests, critères). Reste : rapport réel + calibration.
