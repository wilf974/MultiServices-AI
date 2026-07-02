# Design — IA de curation de la mémoire centrale (« MultiService AI »)

> **Statut : Phase 1 (lecture seule) implémentée le 02/07/2026.**
> Origine : cadrage <user> du 02/07/2026 (`docs/curation/README.md` + `PLAN.md`).
> Prérequis constitutionnel : lever la décision du 21/06 (`d9d7e19c`, session `suite-observation`,
> « pas de couche d'intelligence avant signal réel ») et sa jumelle du 20/06 (`ef345f29`, session
> `observation`) — **par correction C3 dans ces mêmes sessions** (script `scripts/ingest-curation.ps1`).
> Signal constaté au moment de la levée : ~130 décisions / ~45 corrections sur 30 j (cadrage <user>),
> 705 événements/14 j multi-projets. L'idée `project_review()` (20/06, session `roadmap`,
> « APRÈS accumulation de signal ») est recouverte par le rôle Synthèse.

## 1. Architecture (composants, flux, où ça tourne)

```
journal central (jsonl, append-only, bi-temporel)
        │  lecture seule
        ▼
curator.py  ── détecteurs DÉTERMINISTES purs (List[AetherEvent] -> rapport)
        │       doublons exacts · quasi-doublons · gabarits encore valides ·
        │       décisions anciennes non revisitées · contradictions candidates
        ▼
curation_report() ── rapport borné (pattern économie de sortie : k, counts, truncated)
        │                + propositions Phase 2 (schéma ci-dessous, status=pending_human)
        ├─► outil MCP `curation` (lecture seule, D5) — Claude Desktop / postes
        ├─► (plus tard) endpoint webapi central-only  — api-mem.example.com
        └─► (Phase ≥2) narration/consolidation par LLM LOCAL (Ollama, C6)
```

- **Où ça tourne** : les détecteurs sont dans le moteur (`multiservice/`), donc disponibles
  partout où le journal est lisible — poste (stdio), conteneur central (HTTP), VM. Aucun état
  propre : tout est recalculé du journal (pas de 2ᵉ vérité).
- **Choix du modèle (Phase 0, tranché)** : la curation lit le contenu du journal souverain →
  **LLM local uniquement** (Ollama — au choix, jamais figé, décision 01/07). Le déterministe
  d'abord ; le LLM n'arrive qu'en narration/consolidation (C6 : il cite, il n'invente pas).
- **Constitution** : la curation OBSERVE et PROPOSE. Elle n'écrit rien en Phase 1. En Phase 2+,
  toute action passe par les canaux d'écriture existants (memlog-http/ingest), est journalisée
  dans la mémoire elle-même (auditable, bi-temporel), et la fermeture = `valid_to`/supersede,
  JAMAIS suppression (C3).

## 2. Spec des rapports de curation (Phase 1, livré)

`curator.curation_report(events, now, source_prefix, k, older_than_days, near_threshold)` →

| Section | Détecteur | Règle (calibrée sur l'observé) |
|---|---|---|
| `exact_duplicates` | `find_exact_duplicates` | même type + même texte normalisé (accents/casse pliés), ≥ 2 événements VALIDES (C3 respecté). Cas réel : correction licence Apache-2.0 journalisée 2×. |
| `near_duplicates` | `find_near_duplicates` | même type, Jaccard(tokens) ≥ 0.85 (défaut), hors doublons exacts. |
| `placeholder_facts` | `find_placeholder_facts` | faits VALIDES dont le texte est un gabarit non rempli (réutilise `hygiene.looks_like_placeholder`). Cas réel : `<sujet>` en still_standing. |
| `stale_candidates` | `find_stale_candidates` | décisions VALIDES non corrigées, plus vieilles que `older_than_days` (30 déf.) — heuristique d'ÂGE seulement, l'humain juge le contenu. |
| `contradiction_candidates` | `find_contradiction_candidates` | 2 décisions VALIDES de la MÊME session, recouvrement ≥ 0.5 — redondance ou contradiction, à trancher par l'humain. |
| `proposals` | `make_proposal` | UNIQUEMENT pour les doublons exacts (risque minimal), `status=pending_human`. |

Chaque section : bornée à `k` (compteurs complets, `truncated`), chaque item porte ses preuves
(ids, sessions, dates — C2). Le rapport est un dict JSON-sérialisable, PUR, lecture seule.

## 3. Schéma des propositions d'écriture (Phase 2)

```json
{
  "action": "close_duplicate | supersede | review",
  "targets": ["<event_id>", "..."],        // à clore (valid_to) ; jamais supprimés
  "keep": "<event_id>",                     // le survivant (le plus ancien = l'original)
  "rationale": "texte court, autoportant",
  "evidence": {"detector": "...", "score": 1.0, "sessions": ["..."]},
  "status": "pending_human",                // -> approved | rejected (humain, C1)
  "proposed_at": "ISO8601"
}
```
File d'attente Phase 2 : les propositions approuvées sont exécutées via l'ingest (mTLS) comme
événements de curation (`kind=correction`, session de l'original → supersede C3 naturel), chaque
action étant elle-même journalisée. Phase 3 : seule `close_duplicate` STRICTE (texte identique,
même session) devient automatisable, le reste reste supervisé.

## 4. Prompts système de l'IA de curation (Phase ≥ 2, LLM local)

- **Narrateur de rapport (C6)** : « Tu es le curateur de la mémoire MultiService IA. On te donne
  un rapport JSON de détecteurs déterministes. Résume en français factuel, cite les ids, ne
  propose JAMAIS de suppression (C3 : clôture/supersede). N'invente aucun fait absent du rapport. »
- **Comparateur de paires (contradictions)** : « Voici deux décisions de la même session, avec
  dates. Dis si (a) redondantes, (b) contradictoires, (c) complémentaires ; cite le texte ;
  réponds en JSON {verdict, justification}. Dans le doute : (c). »
- Règles dures : local Ollama seulement ; sortie JSON validée ; toute hallucination d'id = rejet.

## 5. Contrat API

- **Livré (Phase 1)** : outil MCP `curation(source, k, older_than_days)` — lecture seule (D5),
  borné, mêmes conventions que `recent`/`lessons`.
- **À venir** : `GET /curation` sur l'API web centrale (token Bearer, mêmes paramètres) ;
  Phase 2 : `POST /curation/proposals/{id}/approve|reject` (humain authentifié, mTLS/token).

## 6. Jeu de tests (livré : `tests/test_curator.py`)

Doublon exact réel (correction ×2) · quasi-doublon paraphrase · gabarit `<sujet>` encore valide ·
décision ancienne (stale) vs récente · contradiction même session · C3 (événement clos exclu) ·
pureté (aucune mutation) · rapport borné/compteurs/truncated · filtre source canonique ·
proposition générée uniquement pour l'exact (status pending_human).

## 7. Critères de validation (passage de phase)

- **Phase 1 → 2** : sur ≥ 20 items signalés revus par l'humain, précision ≥ 90 % pour
  `exact_duplicates`/`placeholder_facts` (proposables), ≥ 70 % de « signalement utile » pour les
  autres sections. Mesure : chaque revue journalise `validation` ou `correction` (kind) avec
  `--session curation-memoire` — la précision se lit ensuite DANS la mémoire (reasoning/lessons).
- **Phase 2 → 3** : ≥ 50 propositions `close_duplicate` approuvées, 0 faux positif sur les
  strictes (texte identique + même session), rollback jamais nécessaire.
- Les seuils (0.85 near-dup, 0.5 contradiction, 30 j stale) sont des DÉFAUTS à recalibrer sur le
  réel après le premier rapport (discipline BITS — jamais à l'aveugle).
