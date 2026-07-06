# Plan d'exécution — MultiService AI mémoire

## Phase 0 — Cadrage (décision préalable)
- Statuer sur la décision « pas de couche d'intelligence avant signal réel » (21/06) : la lever ou définir le seuil de signal atteint (130 décisions / 45 corrections sur 30 j déjà accumulées)
- Choisir le modèle : local (Ollama, souveraineté) vs cloud — cohérent avec l'architecture centrale-only existante

## Phase 1 — Lecture seule (sans risque)
- L'IA produit des rapports : doublons candidats, contradictions, faits probablement périmés, brief par projet
- Aucune écriture ; validation humaine des rapports = mesure de précision

## Phase 2 — Écriture supervisée
- Propositions de consolidation/supersede soumises à validation (file d'attente)
- Journalisation de chaque action de curation dans la mémoire elle-même (auditable, bi-temporel)

## Phase 3 — Autonomie partielle
- Actions à faible risque automatisées (fermeture de doublons stricts) ; le reste reste supervisé

## Livrables socle (à produire avec Fable 5 avant le 07/07)
- Architecture (composants, flux, où ça tourne)
- Spec des rapports de curation + schéma des propositions d'écriture
- Prompts système de l'IA de curation
- Contrat API (endpoints internes ou tools MCP)
- Jeu de tests : cas de doublons/contradictions/péremption attendus
- Critères de validation : précision des propositions ≥ seuil avant passage de phase
