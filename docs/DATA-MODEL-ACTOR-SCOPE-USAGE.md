# Modèle de données — Acteur ≠ Portée + signal d'usage réel

> Statut : **plan validé, non implémenté**. Design issu d'un aller-retour Fable 5 (architecte) ↔
> Claude (critique + ancrage code), 2026-07-07. Chantier « raffinement modèle » (débloque le dashboard
> qualité mémoire & skills). Invariants de `CLAUDE.md` : append-only (jamais de réécriture d'historique),
> lecture pure, provenance (C2), écritures autoritatives humain-gated (C1), souveraineté locale.

## Problème A — séparer *Acteur* et *Portée* sans réécrire l'histoire

Le champ `source` est **surchargé** : il encode À LA FOIS **qui** a écrit (`model:x`/`agent:y`/`human:z`)
ET la **portée** (`project:z`). Ça brouille le recall filtré et les métriques.

### Design (rétro-compatible, zéro réécriture)

- **Champs optionnels** ajoutés à `AetherEvent` (pydantic v2, `None` par défaut → **les vieilles lignes
  valident inchangées**) :
  - `actor: Optional[str]` — qui (`model:x` / `agent:y` / `human:z`)
  - `scope: Optional[str]` — portée (`project:z`)
  - `source` **reste** (provenance telle qu'écrite, rétro-compat).
- **Règle de réinterprétation** = fonction **PURE** `derive_actor_scope(event)`, **jamais** de réécriture
  du journal :
  1. si `actor`/`scope` présents → les utiliser ;
  2. sinon parser `source` : `project:*` → `scope` ; `model:*`/`agent:*`/`human:*`/`llm`/`user` → `actor` ;
  3. **cas ambigu** (ex. `project:bureau` imposé par le CN du cert mais qui encode en fait l'acteur) →
     table **`SOURCE_ALIASES`** (le module **`source_alias.py` existe déjà**) : donnée versionnée, pure,
     curée humain (C1). **Corriger un alias = éditer une donnée dérivée, l'historique ne bouge pas.**
- **Migration = zéro sur le journal** : juste la couche de dérivation + la table d'alias. Les **nouveaux
  writes** remplissent `actor`/`scope` explicitement.

## Problème B — signal d'usage réel sans croire le modèle sur parole

Le modèle auto-déclare mal quels `recalled_ids` l'ont servi. Il faut un signal **fidèle**, **bon marché**,
et surtout **calculé là où il ne dégrade pas**.

### a) Architecture qui tue le problème « central lexical » (critique ④ résolue)

L'attribution a besoin de la **similarité embedding** (pour battre la paraphrase) → elle est un **job
LOCAL-GPU**, exécuté **au moment de la génération**, là où le clair ET le vecteur sont disponibles.

> **Le central ne fait que journaliser le résultat** : un event `usage`
> `{turn_id, recalled_ids, used_ids:[{id,score}], method, attributor_pr}` — une donnée **déjà calculée**.
> Le central **n'attribue jamais**. Le problème « central sans GPU ne peut pas attribuer » **disparaît** :
> ce n'était pas son rôle.

### b) Hiérarchie de signaux par fiabilité décroissante

1. **Fort — id mécaniquement cité** : si le harness peut exiger en sortie structurée les ids utilisés, OU
   si l'injection **tague** les ids et qu'on détecte le tag ré-émis. Ce n'est **pas** « croire le modèle
   sur parole » si c'est **mécaniquement contraint** (l'id doit être cité pour compter). Haute précision.
2. **Moyen — cosinus embedding** (local GPU) : attrape la **paraphrase** (corrige le faux MISS).
3. **Faible — recouvrement lexical pondéré IDF** : n-grammes rares partagés (**TF-IDF, pas Jaccard brut**)
   → tue le faux HIT sur snippets génériques. La paraphrase reste un faux MISS irrécupérable en lexical.

### c) Calibration AVANT de livrer « taux d'usage réel » (doctrine « calibrer sur le réel »)

1. Échantillonner **50–100 tours RÉELS** (pas synthétiques).
2. **Label gold** : humain (ou modèle fort offline) marque quels `recalled_ids` ont réellement informé la complétion.
3. Mesurer **P/R/F1** de l'attributeur par méthode (citation / embedding / lexical), split train/test.
4. Fixer le seuil de score qui maximise F1 sur train, **valider sur test tenu à l'écart**.
5. **Ne publier la métrique QU'ACCOMPAGNÉE du P/R de l'attributeur lui-même** (la métrique ne vaut pas mieux que son extracteur).
6. **Re-calibrer** quand le corpus/domaine de recall dérive.

### d) Fallback lexical acceptable (nœud sans GPU, si l'attribution devait quand même y tourner)

- Pondération **IDF obligatoire** (précision d'abord).
- Traiter le signal comme **borne inférieure** : haute précision, faible rappel (la paraphrase manque).
  L'étiqueter `method="lexical_lowerbound"`.
- **Interdire** de présenter un taux de recall depuis un nœud lexical comme **complet** — c'est un plancher, pas une mesure.

### e) Garde-fou de rayon de souffle

L'event `usage` est **observationnel** (`confidence<1`, `actor=agent`, **jamais autoritatif**). Il **nourrit
le ranking** de `forecast`/`curation`, il **ne clôt rien**. Un signal bruité **dégrade gracieusement un tri**
mais **ne corrompt jamais la vérité du journal**. C'est ce qui rend tolérable un attributeur imparfait — à
condition d'**afficher son P/R au dashboard**.

## Plan de test

| Test | Assertion |
|---|---|
| **split legacy** | table {vieux `source` → `actor`/`scope` attendus} ; `derive_actor_scope()` concorde |
| **précédence alias** | `actor`/`scope` explicites > parse legacy > alias sur ambigu |
| **attribution usage** | complétion contenant le snippet de A seul → `used_ids={A}` ; P/R vs jeu labellisé ; faux positifs bornés sur recall non lié |
| **coût** | attribution `O(k·len)` n-grammes, borné |
| **rétro-compat** | vieilles lignes sans `actor`/`scope`/`usage` valident inchangées |

## Décisions figées

1. `actor`/`scope` = champs **optionnels** (`None` défaut) ; `source` conservé ; **zéro réécriture** du journal.
2. `derive_actor_scope` = fonction **pure** : explicites > parse legacy > `SOURCE_ALIASES` (via `source_alias.py`, curé C1).
3. Attribution d'usage = **job local-GPU** ; le central **journalise** l'event `usage`, il n'attribue jamais.
4. Signaux par fiabilité : id mécaniquement cité > cosinus embedding > lexical IDF (borne inférieure).
5. **Ne jamais livrer** `taux d'usage réel` sans le **P/R de l'attributeur**, calibré sur ≥ 50 tours réels labellisés.
6. Event `usage` **observationnel** (`confidence<1`, `actor=agent`) — nourrit le ranking, ne clôt rien (C1 intact).

### Invariants à coller en tête du prompt du petit modèle

- `derive_actor_scope` est **pure** et ne réécrit jamais le journal ; corriger une ambiguïté = éditer `SOURCE_ALIASES`, pas l'historique.
- L'attribution d'usage tourne **local-GPU** ; le central ne stocke que le résultat.
- La métrique d'usage n'est **jamais publiée seule** — toujours avec le P/R de son extracteur.
- L'event `usage` est **non-autoritatif** : il ne clôt, ne promeut, ne sert jamais rien.
