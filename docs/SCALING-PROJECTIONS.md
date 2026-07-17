# Passage à l'échelle — projections sans renier « journal = vérité, fonctions pures »

> Statut : **P0 + PHASE 1 + PHASE 2 + VECTORIEL BINAIRE + PHASE 3 (snapshots/as-of) IMPLÉMENTÉS** (`multiservice/projection.py` + `multiservice/project.py`, TDD, suite 469 verte).
> P0 : matérialisation SQLite reconstructible, watermark `(line_count, chain_head)` soudé à `integrity.py`
> (préfixe falsifié → rebuild forcé), `search` lexical, `verify_projection` (oracle vs fonction pure).
> Phase 1 (17/07/2026) : **FTS5 trigram sur texte normalisé = PRÉFILTRE sur-ensemble** ; les fonctions
> pures de `memory` restent LE moteur (scores, C3, tri, snippets) — le SQL ne fait que restreindre la
> liste d'events fournie (candidats + toutes les corrections C3), d'où l'égalité oracle par construction.
> Routage : `recall_sql`/`recent_sql`/`brief_sql` + `for_journal` ; surface MCP branchée (repli
> fonctions pures si projection indisponible). Vérifié sur le journal réel (2 621 events, oracle ÉGAL).
> Phase 2 (17/07/2026) : **updater incrémental hors du chemin de lecture** — `python -m
> multiservice.project` (one-shot post-append, `--status`/`--rebuild`/`--verify` CI avec code retour,
> `--watch` tail-watcher qui ne relit le journal que si son stat (taille, mtime) change). Tamper
> pendant le watch → rebuild forcé (hérité de `Projection.update`) ; l'updater n'écrit JAMAIS le
> journal (test). Smoke réel : rattrapage 2 621 lignes, `--verify` OK, statut FRESH.
> Vectoriel binaire (17/07/2026, décision `0407c17a`, **local only**) : table `vecs(id, bits)` =
> quantization binaire maison (1 bit/dim signe, 128 o/vecteur, XOR+popcount pur Python — **sans
> sqlite-vec** : zéro dépendance native, brute-force en millisecondes à notre échelle). Le jsonl
> `EmbeddingStore` **garde les float32** (vérité reconstructible) ; le top-M Hamming n'est qu'un
> préfiltre de plus (union candidats FTS ∪ top-M ∪ corrections C3), re-score float32 dans le pur
> (`qvec` réutilisé, une seule passe d'embedding). **Calibré sur le réel** (2 379 vecteurs bge-m3,
> 100 requêtes) : recall@10 dans le top-M = 96,3 % (M=40) · **99,1 % (M=80, défaut)** · 99,5 %
> (M=120) ; préfiltre 2,9 ms vs 182 ms de cosinus exact (×63). `evict` (crypto-shredding RGPD)
> **propagé** par `sync_vectors` (les bits dérivent du clair effacé). Sync : `python -m
> multiservice.project --vectors` après `python -m multiservice.index`. Surface MCP branchée.
> Phase 3 (17/07/2026) : **snapshots + as-of par temps valide** — oracle pur `memory.as_of`
> (valid_from/valid_to + clôtures ciblées `data.closes` en vigueur à T ; le supersede-session reste
> un drapeau de lecture, pas une clôture) ; table `closures` (fold des clôtures, couverte par
> `state_hash`/`verify`) ; `take_snapshot(T)` (état actif figé, refigeable — ne dérive que du
> journal) ; `as_of_sql` = snapshot le plus proche ≤ T + **delta par temps valide** (pas par ligne :
> un event rétro/futur-daté appendé tôt reste attrapé) + overlay (corrections + leurs **cibles**
> candidates : une clôture elle-même close ressuscite sa cible) → sur-ensemble par construction,
> le pur tranche, **égalité oracle**. Correction C3 tardive : reflétée **sans rebuild** (testé).
> Rebuild forcé (tamper) → **snapshots purgés** (jamais d'état figé dérivé d'un préfixe inconnu).
> CLI : `--snapshot [ISO]` · `--as-of ISO`. **Vérifié sur le réel** (2 621 events) : égalité
> SQL == pur sur les 4 chemins (repli, snapshot exact, snapshot+delta 9 j, delta à maintenant) ;
> 2 550 actifs au 17/07, 24 au 17/06. 8 tests (`tests/test_projection_asof.py`), suite 469 verte.
> Exploitation : tâche planifiée `MultiServiceAI-Projection` (15 min, `scripts/install_project_update.ps1`)
> = rattrapage `run_once` + `--vectors` — fin des reprises STALE.
> Design issu d'un aller-retour Fable 5 (architecte) ↔ Claude (critique + ancrage code), 2026-07-07.
> Invariants de `CLAUDE.md` : journal append-only source unique, tout dérivé reconstructible,
> lecture pure, bi-temporalité (C3), souveraineté locale, chaîne de hachage (`integrity.py`).

## 0. Principe directeur

Aujourd'hui chaque lecture fait `read_events()` sur **tout** le journal en mémoire (fonction pure sur la
liste complète). Ça ne tient pas à 1M+ events. Solution :

> **Le journal reste la vérité ; tout dérivé est un `fold(journal)` mémoïsé avec un watermark.**
> Les fonctions pures actuelles **ne meurent pas** : elles deviennent l'**oracle de correction** des
> projections (le test de reconstruction, c'est elles).

## 1. Projections matérialisées (Q1)

| Projection | Backend | Portée |
|---|---|---|
| **Lexical** | SQLite **FTS5** : `events_fts(id, text, source, type, valid_from, valid_to)` | **Partout** (central sans GPU inclus) |
| **Vectoriel** | `sqlite-vec` (ou le jsonl actuel) | **Local only** (embeddings GPU) |
| **Agrégats** | table `active_state(id, is_active, superseded_by, valid_from, valid_to)` | Partout |

Répond à la contrainte GPU : **vecteur = local only**, **lexical = partout** ; `recall_semantic` **dégrade en
lexical** si pas de vecteur (déjà le comportement actuel).

**Garantie de reconstructibilité + son test** : une projection = `reduce` pur sur les lignes.
`verify_projection(journal)` recompute *from scratch* et compare un **hash du row-set** à l'état
incrémental. **Égalité = preuve.** C'est **LE** test de reconstruction exigé par la doctrine, et il doit
tourner **en CI**.

## 2. Watermark + lecture incrémentale (Q3) — soudé à `integrity.py`

- Chaque projection stocke `applied_through = (line_count, chain_head)`.
- Update = relire **seulement** les lignes après `line_count` (offsets stables car append-only).
- **Lier le watermark à `chain_head`** (de `integrity.py`) : si le préfixe du journal a changé (tamper /
  réécriture), le head ne concorde plus → la projection **refuse l'update incrémental et force un rebuild**.
  Ça soude ce chantier au tamper-evidence : une projection ne peut pas propager silencieusement une
  falsification.

## 3. Snapshots + requête as-of (Q2) & corrections tardives (Q3)

- **Snapshot** = `active_state` figé à `(T, line_count)`, persisté. `as-of(T')` = snapshot le plus proche
  ≤ T' **+ delta** jusqu'à T'. On évite de rejouer depuis genesis.
- **Deux temps distincts** : l'application incrémentale suit l'**ordre d'append** (`observed_at`, temps de
  transaction), mais les requêtes `as-of` suivent le **temps valide** (`valid_from`/`valid_to`).
- **Correction C3 tardive** (rétro-datée : arrive maintenant mais clôt un fait ancien) : **pas de rebuild**.
  `active_state` applique juste le `valid_to` (incrémental, *cheap*). Pour les `as-of` :
  `as_of(T) = snapshot(T)` **puis overlay** des corrections dont `valid_from ≤ T` **quelle que soit leur
  date d'arrivée**. Les corrections sont rares et petites → overlay bon marché, correction exacte sans
  rebuild total.

> **Précondition validée (critique Claude)** : l'overlay reste bon marché *parce que* les corrections sont
> rares (~93 sur le journal réel). Si elles explosaient, le bénéfice des snapshots s'éroderait — à
> surveiller, mais c'est une hypothèse **vérifiée** sur le corpus, pas un pari aveugle.

## 4. Migration depuis le tout-en-mémoire

- **Phase 0** : `read_events()` reste le fallback.
- **Phase 1** : construire la projection SQLite **une fois** ; router `recall`/`recent`/`brief` vers SQL ;
  les fonctions pures servent d'**oracle** (test : résultat SQL == résultat fonction pure sur le même journal).
- **Phase 2** : updater incrémental (commande `project` post-append, ou tail-watcher). **FAIT** :
  `multiservice/project.py` (`run_once`/`status`/`watch` + CLI, 9 tests).
- **Phase 3** : snapshots pour `as-of`. **FAIT** : `memory.as_of` (oracle pur), `take_snapshot`,
  `as_of_sql` (snapshot + delta + overlay), purge des snapshots au rebuild, CLI `--snapshot`/`--as-of`
  (8 tests, `tests/test_projection_asof.py`).

## 5. Plan de test (vérifiable)

| Test | Assertion |
|---|---|
| **oracle** | ∀ requête, projection SQL == fonction pure (sur le même journal) |
| **incrémental == batch** | appliquer par lignes == rebuild → **même hash d'état** |
| **as-of** | `snapshot + delta + overlay` corrections == `fold as-of` pur |
| **correction tardive** | append C3 rétro-daté → `as-of(T)` la reflète **sans rebuild** ; invalidation snapshot correcte |
| **watermark / tamper** | préfixe modifié (`chain_head` ≠) → **refus** d'update incrémental (force rebuild) |

## Décisions figées

1. Journal = vérité ; projection = `fold` mémoïsé + watermark. Les **fonctions pures = oracle** de la projection.
2. `verify_projection` (recompute vs incrémental, égalité de hash) tourne **en CI** — la projection n'est jamais une nouvelle source de vérité.
3. Watermark = `(line_count, chain_head)` ; `chain_head` divergent → **rebuild forcé** (soudé à `integrity.py`).
4. Lexical (FTS5) **partout** ; vectoriel (sqlite-vec) **local only** ; `recall_semantic` dégrade en lexical sans vecteur.
5. `as-of` = snapshot + overlay des corrections par **temps valide** ; correction tardive = pas de rebuild.

### Invariants à coller en tête du prompt du petit modèle

- Une projection ne devient **jamais** la source de vérité : `verify_projection` doit passer en CI, l'oracle reste les fonctions pures.
- Watermark lié à `chain_head` : tout changement de préfixe → rebuild, jamais d'update incrémental sur un journal falsifié.
- `as-of` suit le **temps valide** (`valid_from`/`valid_to`), l'application incrémentale suit l'**ordre d'append** — ne pas confondre les deux.
