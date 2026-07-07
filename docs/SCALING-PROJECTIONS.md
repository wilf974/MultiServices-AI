# Passage à l'échelle — projections sans renier « journal = vérité, fonctions pures »

> Statut : **P0 IMPLÉMENTÉ** (`multiservice/projection.py`, TDD, 6 tests, suite 431 verte). Livré :
> matérialisation SQLite reconstructible, watermark `(line_count, chain_head)` soudé à `integrity.py`
> (préfixe falsifié → rebuild forcé), `search` lexical, `verify_projection` (oracle vs fonction pure).
> **Différé** : FTS5/sqlite-vec, snapshots/as-of, routage de `recall`/`recent`/`brief` vers SQL.
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
- **Phase 2** : updater incrémental (commande `project` post-append, ou tail-watcher).
- **Phase 3** : snapshots pour `as-of`.

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
