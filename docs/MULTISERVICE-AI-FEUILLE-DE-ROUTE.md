# MultiService AI — Feuille de route

> Le « quand ». À lire après VISION et CONCEPTION ; décisions dans `DECISIONS.md`.
> Format calé sur ta culture de sprints (Sprint 12 = Predictive N0, 179 tests verts).
> **Discipline cardinale (leçon BITS) : observer le réel AVANT de calibrer.**
> Daté : 16 juin 2026. Statut : cadre figé, séquence à confirmer en chemin.
> **MAJ 19 juin 2026 — feuille de route COMPLÈTE : S13→S18 + O1b livrés, 91 tests verts.**
> Détails d'exécution dans `DECISIONS.md`. Reste uniquement le transverse (multi-fournisseurs).

---

## 0. Règles du jeu (héritées, non négociables)

- **Chaque sprint laisse un test de régression permanent.**
- **On observe avant de calibrer** (sinon = 137 faux positifs BITS, 2e édition).
- **Le Plan de Contexte ne mute jamais le journal** — test structurel à chaque étape.
- **Sorties console ASCII** ; `.md` accentués.
- **Pas de `git commit` depuis le bac à sable** (troncature) — committer côté Windows.

---

## 1. Séquence des sprints

L'ordre **respecte la discipline** : capturer d'abord, mesurer ensuite, optimiser enfin.
Aucun seuil calibré tant qu'on n'a pas vu plusieurs jours de réel.

### Sprint 13 — Capture via routeur minimal (observer) · *fondation*
**But.** Faire entrer le flux LLM dans le journal, sans rien servir encore.
- Squelette du **routeur** : interface `generate()` + **un** backend (le plus simple à
  câbler — `EmbeddedGGUF` in-process *ou* un backend API selon ce qui est sous la main).
- Nouveaux types : `prompt`, `completion`, `tool_call`, `tool_result`, `correction`,
  `token_usage` — datés, sourcés, bi-temporels.
- **Rien d'autre.** Pas de recall, pas de cache, pas de détecteur. *On observe.*
- **Régression** : aller-retour de capture + intégrité C2/C3 (provenance + bi-temporalité
  sur 100 % des événements capturés) ; **`count_source` présent** sur chaque `token_usage`.

### Sprint 14 — Surface MCP en lecture seule (`recall`/`why`/`briefing`)
**But.** Le LLM peut *tirer* la mémoire ; il ne mute rien.
- Serveur MCP : `resources` (recall, why par entité, briefing) + `tools` (recall, why).
- Première brique de la 2e surface (Claude.ai/ChatGPT.com peuvent lire le substrat).
- **Régression** : (a) restitution **provenance-attachée et bi-temporelle** ; (b) **test
  structurel** « aucun tool ne mute le journal » (modèle `test_predict.py`).

### Sprint 15 — Comptabilité de tokens (`economy`) · *mesurer*
**But.** Savoir où partent les tokens. Pas encore d'optimisation — on **mesure.**
- Module `economy` : tokens/tour, tokens/**tâche**, part redondante, **agrégé par
  `(model_id, count_source)`**, jamais sommé à travers les bases.
- Premiers détecteurs de gaspillage tournés vers le contexte (SPOF-contexte, fenêtre muette)
  **en mode rapport seulement**, seuils observés, pas appliqués.
- Bloc `Usage:` dans le briefing (tokens dépensés, % redondant estimé).
- **Régression** : la compta **réconcilie** (somme cohérente *par base*) ; détecteur de
  redondance sur une *fixture* connue.

### Sprint 16 — Backend `EmbeddedGGUF` in-process + économie réelle · *les vraies économies*
**But.** Économiser pour de vrai en local : **result-cache + clôture C3** (indépendants de
l'architecture), réutilisation KV en **bonus opportuniste** selon le GGUF chargé.
- Backend `EmbeddedGGUF` (`llama-cpp-python`, n'importe quel `.gguf`, in-process, zéro réseau).
- **Cache de résultat** (exact d'abord) : clé `hash(prompt) + provenance` ; **toute clôture
  C3 d'un fait contribuant invalide l'entrée**.
- **Clôture C3 agressive** en composition (pointeur compact + journal verbatim) → prompt court.
- `LlamaRAMCache`/`LlamaDiskCache` activés (bonus préfixe *si* le modèle le supporte ; **ne
  pas s'y fier** pour Gemma 4 — SWA).
- **Régression** : (a) la clôture ne **perd jamais** de donnée (rejouable) ; (b) le cache ne
  sert **jamais** un résultat périmé (garde C3) ; (c) **test structurel** « le cœur du
  backend ne contient pas d'I/O hors `generate()` » (dérogation pureté, §10 conception).
- **Topologie (tranché)** : Gemma sur le **Poste Windows** (couplage SPOF assumé, documenté).

### Sprint 17 — Skills émergentes (suggérer, l'humain promeut)
**But.** Cristalliser des skills à partir des patterns réels — **après** avoir vu le réel.
- Détecteur de rafale `tool_call`/`tool_result` (**neuf**) → unité « tâche ».
- Patterns récurrents → `skill_candidate` (`type=suggestion`). **v1 = observé seul** ;
  candidates-LLM en **quarantaine séparée** (séparation par `source`).
- Promotion **manuelle** → skill `SKILL.md` versionnée et bi-temporelle. Seuil `1−0.5^n`,
  **calibré sur l'observé** (BITS).
- **Régression** : (a) cristallisation = **suggestion seule**, jamais auto-appliquée ;
  (b) skill promue **versionnée et bi-temporelle** ; (c) péremption détectée (fenêtre muette
  / pic de corrections / preuve rétrécie) **n'auto-supprime jamais** — clôture C3, revue humaine.

### Sprint 18 — Cache avancé + pré-chauffage + replay (`predict`/`why` vers l'avant) ✅ LIVRÉ (19 juin 2026)
**But.** Court-circuiter le modèle quand c'est sûr ; anticiper ; répondre « pourquoi l'agent
a vu ça ».
- ✅ Cache **sémantique** mûr (`semcache.py`, court-circuit sur hit fiable, garde C3 ; seuil 0.95
  **calibré sur le réel** via `semcache_probe.py`).
- ✅ **Pré-chauffage** (`preheat.py`) : estime le contexte/coût du prochain tour (snowball vs
  fenêtrage C3). **Lecture seule.** Outil MCP `forecast`.
- ✅ **Replay (neuf)** (`memory.replay_event`) : traversée *event → chaîne causale*. Outil MCP
  `replay_event`. (`why` reste par tour, `replay` par session.)
- ✅ **Régression** : (a) cache — périmé/voisinage → non servi ; (b) pré-chauffage **ne mute
  rien** ; (c) replay **ne mute rien**, cite ses preuves. `test_replay_s18` + `test_semcache_s18`
  + `test_preheat_s18` (18 tests), **91 verts au total**.
- **Validé en live via le MCP** (test poussé 19 juin) : `recall` (+ filtres type/source),
  `recall_semantic` (explain), `why`, `replay`, `replay_event` exercés sur le vrai journal.
  `forecast` à vérifier au prochain redémarrage de Claude Desktop.

### (Transverse) Routeur multi-fournisseurs complet + 2e surface
- Backends `Claude` / `ChatGPT` ajoutés dès qu'utile (la capture marche pour eux dès S13/14).
- **Politique « sensible → local seul »** appliquée par le routeur.
- Prompt-caching cloud exploité (router le prefix-heavy vers le cloud — là où Gemma le refuse).
- Serveur MCP exposé à Claude.ai/ChatGPT.com (accès mémoire/skills ; économie côté cloud only).

---

## 2. Tableau de synthèse

| Sprint | Thème | Sert au LLM ? | Optimise ? | Test de régression clé |
|---|---|---|---|---|
| 13 | Capture via routeur min. | non | non | intégrité C2/C3 + `count_source` |
| 14 | Surface MCP (lecture) | oui (lecture) | non | aucune mutation du journal |
| 15 | Comptabilité tokens | — | non (mesure) | réconciliation par base + redondance |
| 16 | `EmbeddedGGUF` + result-cache + C3 | oui | **oui** | clôture sans perte + cache non périmé + pureté backend |
| 17 | Skills émergentes | oui | oui | suggestion seule + skill versionnée + péremption sans auto-suppression |
| 18 | Cache+ / pré-chauffage / replay | oui | **oui** | exactitude cache + lecture seule predict/replay |

> Toute l'optimisation **après** la mesure. C'est ce qui t'a évité les faux positifs BITS,
> transposé au domaine LLM.

---

## 3. Les défis — état au 16 juin 2026

Les arbitrages figés sont dans `DECISIONS.md`. Récapitulatif :

| # | Défi | État |
|---|---|---|
| 1 | Apprendre de tout vs économiser ; vectoriel | **Figé (D14)** : recall hybride, vectoriel additif/suggestif, **embedding local**. Tiering = **ouvert (O3)**. |
| 2 | « Sans API » | **Figé (D1)** : (a)+(c). |
| 3 | Tokenizer hétérogène | **Figé (D9)** : hétérogène mais honnête, `count_source`. Local dissous par l'in-process (D4). |
| 4 | File empoisonnable | **Figé (D10)** : v1 observé seul, séparation par `source`, quota+dédup+`1−0.5^n`, promotion humaine. |
| 5 | Gain cache dépend de la pile | **Figé (D6/D7)** : économie = result-cache + clôture C3 ; KV de préfixe = bonus opportuniste (pas pour Gemma/SWA). |
| 6 | Sur-apprentissage / mort des skills | **Figé (D10/D11)** : `1−0.5^n` ; péremption = 3 signaux déterministes ; clôture C3, jamais suppression. |
| 7 | Mesurer la valeur (tokens/tâche) | **Figé (D12)** : id de session sinon fenêtre+corrélation ; détecteur de rafale neuf. |

**Ouverts restants** : O1 GPU (tranché Windows, mitigation future) · O2 backend dense
cache-friendly (optionnel) · O3 tiering · O4 Neo4j à l'échelle.

---

## 4. Ce qui débloque le Sprint 13

Tout le cadre est figé (`DECISIONS.md`). Sprint 13 = **capture via routeur minimal**, un
seul backend, types d'événements + intégrité C2/C3. On regarde le réel. Puis on calibre.
Comme d'habitude.
