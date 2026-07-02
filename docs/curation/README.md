# MultiService AI — IA dédiée à la mémoire centrale

## Idée
Créer une IA dédiée « MultiService AI » pour gérer la mémoire centrale de façon **dynamique** : curation, consolidation, correction, synthèse — au lieu d'une mémoire purement passive interrogée à la demande.

## Origine
Résumé fourni par <user> le 02/07/2026 (réf. `62cd6759`, non retrouvée dans la mémoire centrale).

## Ce que la mémoire centrale confirme (vérifié)
- L'infra existe : MCP multiservice-memory, journal central multi-projets, bi-temporel (valid_from/valid_to), corrections C3, index sémantique Ollama, ingest memlog-http mTLS, API REST web en cours (`feature/webapi-rest`, api-mem.example.com)
- Économie de sortie décidée le 01/07 (plafonds, sorties 70-80 Ko en crise) — une IA de curation réduirait ce problème à la source
- ⚠️ Tension avec une décision active (21/06, `d9d7e19c`) : « dogfooder le MCP plusieurs semaines et NE PAS ajouter de couche d'intelligence avant signal réel ». Cette idée doit soit attendre le signal, soit être cadrée comme la levée explicite de cette décision.

## Rôles possibles de l'IA
1. **Curation** : dédoublonnage, consolidation, fermeture bi-temporelle des faits périmés
2. **Synthèse** : `project_review()` automatisé, briefs par projet (recouvre l'idée `project-review-vue-composee/`)
3. **Hygiène** : fraîcheur d'index, détection de contradictions, provenance
4. **Routage** : choisir quoi mémoriser (signal vs bruit) au fil des sessions

Voir `PLAN.md`.
