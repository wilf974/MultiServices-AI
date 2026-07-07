# MultiService IA

> **Les LLM oublient. Votre mémoire ne devrait pas.**
>
> *Un substrat de mémoire souverain pour LLM — une force, pas une dépendance.*

*([English version](README.md))*

<p align="center">
  <img src="docs/dunkbot-payoff.gif" alt="Démo MultiService IA : une décision périmée corrigée par la mémoire" width="720">
</p>

**Même question. Même historique. Deux réponses différentes.**  
La différence ? L'une sait qu'une décision a été corrigée.

Sans mémoire, l'agent re-recommande un moteur **abandonné**. Avec MultiService IA, il voit que la
décision a été **corrigée (C3)**, sert la **vérité courante**, et affiche sa **provenance** et sa
**fraîcheur** — la mémoire ne suffit pas ; l'avantage, c'est **mémoire + provenance + fraîcheur**.

MultiService IA observe chaque tour d'une conversation LLM (prompt / complétion / appels d'outils /
tokens), le mémorise comme un événement daté, sourcé et bi-temporel, puis le **restitue** (recall),
l'**explique** (why / replay), l'**économise** (cache / fenêtrage de contexte) et l'**anticipe**
(pré-chauffage) — le tout **localement**, sous un contrat strict de lecture seule.

Il transforme un chat sans mémoire en une mémoire qui t'appartient : interrogeable, auditable,
honnête sur sa propre fraîcheur — sans jamais expédier tes données où que ce soit.

---

## Quel problème ça résout ?

**Sans mémoire :**

- les agents répètent des décisions abandonnées
- le contexte est ré-envoyé à chaque tour
- le raisonnement passé disparaît

**Avec MultiService IA :**

- les faits périmés sont détectés
- les corrections deviennent des événements de première classe
- chaque réponse peut expliquer d'où elle vient

---

## Pourquoi

Une conversation avec un LLM est éphémère par défaut : le contexte est ré-envoyé à chaque tour, la
connaissance se perd entre les sessions, et on ne peut pas demander *pourquoi* le modèle a répondu
ceci il y a trois jours. MultiService IA corrige cela avec une idée simple, empruntée à
l'event sourcing : **ajouter chaque tour à un journal local append-only, et ne jamais rien
supprimer.** À partir de ce journal, tout le reste (recherche, explication, économie, prévision)
n'est qu'une lecture pure.

> Une mémoire classique répond **« qu'est-ce que je sais ? »**. MultiService IA peut aussi répondre
> **« qu'est-ce qui est encore vrai ? »**, **« qu'est-ce qui a été corrigé ? »**, **« pourquoi ? »**
> et **« cette décision a-t-elle été validée ? »** — via `reasoning()`, `lessons()` et `replay_event()`.

---

## En 30 secondes

```text
Sans mémoire          →  recommande encore le NEMA-17 (la 1re idée venue)
Avec MultiService IA  →  détecte que le NEMA-17 a été corrigé
                      →  recommande le MG996R + réducteur 2:1
                      →  explique pourquoi (le bras calait)
                      →  montre la provenance et la fraîcheur
```

La plupart des mémoires d'agent montrent des diagrammes. Ici on montre une **conséquence
concrète** : éviter de servir une décision devenue fausse, sans jamais perdre l'historique.

---

## Principes (non négociables)

Gravés dans le code et vérifiés par des tests :

- **Provenance obligatoire.** Chaque événement porte une `source` non vide. Aucun fait sans origine.
- **Bi-temporalité, jamais de suppression.** Les événements ont un `valid_from` ; une correction
  *clôture* un fait (`valid_to`) sans jamais l'effacer. La vérité d'hier reste interrogeable
  « telle qu'on la voyait alors ».
- **La mémoire observe ; elle ne juge ni n'agit.** La capture est fidèle et totale. Le filtre vient
  plus tard, au niveau *promotion* et *service*, tenu par un humain.
- **Les chemins de lecture sont en lecture seule.** Recall, replay, prévision et briefing n'écrivent
  jamais le journal, ne mutent jamais d'état. Un test structurel le garantit.
- **Souveraineté.** Inférence et embeddings sont **100 % locaux** (via [Ollama](https://ollama.com)).
  Aucune API d'inférence ou d'embedding hébergée n'est requise ni utilisée.

La séparation saine que le projet préserve :

> **Capture mémorise · Recall restitue · Replay explique · Preheat anticipe · l'Humain tranche.**

---

## Comment ça marche

```
 tour de chat ─▶ routeur ─▶ AetherEvent(s) ─▶ journal append-only (.jsonl)
                                                   │
                          ┌────────────────────────┼─────────────────────────┐
                          ▼                         ▼                          ▼
                   recall / brief            replay / replay_event       forecast / economy
                   (trouver, R/O)            (expliquer, R/O)            (anticiper, R/O)
                                                   │
                                       embeddings locaux (bge-m3)
                                       pour le recall sémantique hybride
```

Chaque tour devient un `prompt`, une `completion` et un `token_usage`, partageant un `turn_id` et un
`session_id`. Le journal est la source unique de vérité ; le reste du système est un ensemble de
**fonctions pures** (`List[AetherEvent] → résultat`). La seule pièce à effet de bord est le backend
d'inférence/embedding, volontairement isolé.

---

## Démo concrète — DunkBot 3000 🥞🤖

![Démo Memory Arcade](examples/memory_demo/arcade_demo.gif)

Une démo **100 % fictive** (aucune donnée réelle) montre la valeur en une image : **la même
question, sans mémoire puis avec.** On monte un robot à pancakes ; jour 1 on décide un moteur
**NEMA-17**, jour 3 le terrain corrige (*« il cale → servo MG996R »*).

```bash
python examples/memory_demo/compare.py
```

```text
SANS MultiService IA  (agent sans mémoire)
  -> Réponse à l'aveugle. Au pire, il re-propose le NEMA-17 sans savoir qu'il a été abandonné.

AVEC MultiService IA  (mémoire locale, lecture seule)
  brief() — un seul appel :
    DECISION  [PÉRIMÉ C3 !] : DunkBot ... NEMA-17 ...
    -> révisé depuis (corrected_by) : la décision ci-dessus n'est PLUS la vérité.
  VÉRITÉ COURANTE (correction) : ... passer à un servo MG996R + réducteur 2:1.
  Code retrouvé (has_code) / Nomenclature (has_table) ... sourcés et datés.
```

**La morale :** sans mémoire, l'agent risque de re-recommander le moteur **périmé** ; avec la
mémoire + le drapeau bi-temporel **C3**, il sert la vérité courante, sourcée et datée.

Et un **GUI** fun et autonome (aucun serveur) : ouvre **`examples/memory_demo/arcade.html`** dans un
navigateur — tape une question, vois les deux panneaux côte à côte, le fait périmé **rayé** (C3) et
la timeline append-only. Détails : [`examples/memory_demo/`](examples/memory_demo/README.md).

---

## Dogfooding : la mémoire se souvient de sa propre évolution

MultiService IA est utilisé pour suivre MultiService IA lui-même. Quand la licence du projet est
passée de **MIT** à **Apache-2.0**, l'ancienne décision a été **clôturée, jamais supprimée**, et
`lessons()` a fait remonter la vérité courante.

<p align="center">
  <img src="docs/license-payoff.gif" alt="MultiService IA se rappelle sa propre décision de licence : MIT, corrigée en Apache-2.0" width="720">
</p>

Trente jours plus tard, `recall("license")` renvoie la **vérité courante** (Apache-2.0) et marque
**MIT en `STALE (C3)`**, tandis que `lessons()` conserve le **pourquoi**. Chaque image de ce clip est
un événement réel du journal — pas une démo fictive. *(Vidéo complète 34 s : [`docs/license-demo.mp4`](docs/license-demo.mp4).)*

---

## De la mémoire à la connaissance

MultiService IA n'est pas qu'un historique de chat. Au fil des semaines et des mois, le journal
accumule **décisions, corrections, hypothèses, observations et validations** — toutes typées,
sourcées et datées. Cela permet à une **session d'agent neuve, sans aucun contexte préalable, de
reconstruire l'état d'un projet à partir de la seule mémoire.**

<p align="center">
  <img src="docs/from-memory-to-knowledge.png" alt="Une session d'agent neuve, sans contexte préalable, reconstruit l'état d'un projet depuis la mémoire : théorie courante, résultats clés, corrections (STALE C3), hypothèses réfutées, erreurs classées (bugs / méthodologie / résultats négatifs), et où reprendre." width="760">
</p>

L'agent ne rappelle plus des faits isolés — il reconstruit l'**histoire intellectuelle** d'un
projet : ce qu'on croyait, ce qui était faux, ce qui a été corrigé, ce qui a été validé, et
*pourquoi*. Un moteur de recherche renvoie des documents ; ceci renvoie un **briefing**. C'est pour
cela que les événements sont **typés, sourcés, datés et jamais supprimés** : la connaissance émerge
du journal, et le journal reste l'unique source de vérité.

---

## La surface de mémoire

Le substrat expose une surface en **lecture seule** (par ex. via [MCP](https://modelcontextprotocol.io)
vers un client compatible). Tous les résultats portent leur provenance et un drapeau de fraîcheur.

| Outil | Rôle |
|---|---|
| `recall(query, …)` | Souvenirs pertinents. Filtres : type, source, et **structure** (`has_code`, `has_table`). Chaque résultat porte `superseded` / `corrected_by` (révisé depuis ?). |
| `recall_semantic(query, …)` | Recall hybride : couverture lexicale **+** embedding sémantique local, fusionnés avec un plancher anti-bruit. Le mode `explain` détaille les sous-scores. |
| `sources()` | **Carte de toute la mémoire** : chaque namespace/source (`project:*`, `llm:*`, …) avec son nombre d'événements — pour voir *ce qui existe* avant de chercher. |
| `browse(source, type, k)` | **Énumérer sans requête** : entrées filtrées par source/type, plus récentes d'abord — pour explorer un projet entier là où le recall lexical ne matcherait pas. |
| `why(turn_id)` | Les événements d'un tour — « pourquoi l'agent a vu/dit ça ». |
| `replay(session_id, digest=True)` | Rejoue une session : résumé compact (1 ligne/tour) par défaut, ou dump complet. |
| `replay_event(event_id, depth)` | La **chaîne causale** d'un événement : tour focus + tours précédents + clôture/corrections C3. |
| `forecast(session_id)` | **Pré-chauffage** : projette le coût du prochain tour (snowball vs fenêtré), estimation en lecture seule. |
| `brief(query, k)` | Un brief de sujet composé en un appel : souvenirs + décisions liées + éléments révisés + sessions. |
| `recent(days)` | **« Quoi de neuf »** : décisions, corrections et derniers événements récents — le point d'entrée d'une reprise. |
| `reasoning(session_id)` | **fil de raisonnement** d'une session : hypothèse → observation → décision → correction → validation, ordonné, avec **étapes présentes/manquantes** (ex. décision sans validation) |
| `lessons()` | **Leçons** tirées des corrections C3 : ce qui a été révisé/abandonné + les vérités qui tiennent encore. Vide tant qu'aucune correction n'est journalisée. |
| `curation(source, …)` | **Rapport de santé** (lecture seule) : doublons exacts/quasi, gabarits non remplis, décisions périmées, contradictions candidates — chacun avec ses preuves et des propositions de clôture prêtes (`pending_human`). |
| `project_review(project, …)` | **Revue composée d'un projet** (lecture seule) : reconstruit l'état d'un projet depuis la seule mémoire — décisions valides vs corrigées (avec le *pourquoi*), hypothèses réfutées / debout, validations, leçons. Bornée, bi-temporelle. |
| `health()` | **Santé du substrat** (lecture seule) : disponibilité, nombre d'événements, dernier événement, nombre de sources — le point d'entrée d'une reprise (`health → recent → recall`). |
| `index_status()` | Fraîcheur de l'index sémantique (`eligible` / `indexed` / `fresh`). Indique quand le recall sémantique est partiel. |
| `usage()` | **Instrumentation** de réutilisation : combien de tours servis depuis la mémoire (cache, sans modèle) et tokens épargnés. Mesure, ne prédit pas. |
| ressource `briefing/today` | Briefing d'usage du jour (tokens, économie de compaction, par modèle). |

Deux chemins d'écriture validés par l'humain vivent dans la boucle de chat (hors de la surface
lecture seule) :

- `/correct <note>` — enregistre une `correction`, marquant les souvenirs antérieurs de la session
  comme révisés (C3).
- `/note <texte>` — enregistre une note proposée par l'agent (`source=agent:claude`), **validée par
  l'humain qui lance la commande** (C1). La mémoire peut ainsi *compounder* à partir du raisonnement
  de l'agent, tandis que la surface d'interrogation reste strictement en lecture seule.

---

## Mémoire agentique — le modèle cherche (et se souvient) lui-même

Au-delà de la surface lecture seule, un modèle **local** (via le function-calling d'Ollama) peut
piloter la mémoire **lui-même** : il décide quand il lui faut un souvenir, appelle `recall` /
`sources` / `browse` / `recent` / …, lit les résultats et répond — sans injection côté hôte. Chaque
appel d'outil est journalisé (`tool_call` / `tool_result`), donc auditable : on voit *ce que le
modèle a cherché*.

Il peut aussi **écrire**, via un unique outil gardé — `remember(text, kind)` :

- **source forcée** à `project:ollama` (le modèle ne peut usurper une autre source),
- **append-only / bi-temporel** — il consigne, ne supprime jamais,
- **non-autoritatif** — kinds limités à `observation` / `note` ; les kinds autoritatifs
  (`decision` / `validation` / `correction`) restent **validés par l'humain (C1)**. Les écritures du
  modèle ne sont jamais promues en skill ni servies par le cache décisionnel,
- **dédupliqué**.

Le modèle obtient une vraie surface lecture+écriture **sans** casser *« la mémoire observe, l'humain
tranche »* : ses écritures sont isolées par source, non destructives, non-autoritatives. À lancer
dans la boucle de chat avec `--memory-tools`, ou depuis la console web locale (ci-dessous).

> **Souveraineté des outils.** Les outils mémoire ne sont exposés **que pour un tour local**. Si un
> tour part vers un fournisseur cloud, aucun outil mémoire n'est exposé et rien de sensible n'est
> embarqué dans le contexte d'outils — la mémoire ne quitte jamais la machine.

---

## Routage multi-fournisseurs (optionnel — local d'abord)

Par défaut, tout est local. **En option**, un backend cloud peut être activé derrière la même
interface `Backend`, gouverné par une politique hybride **« sensible → local seul »** :

- **local par défaut** ; un tour part au cloud **seulement si** tu l'autorises explicitement **et**
  qu'un détecteur déterministe ne trouve rien de sensible (secrets, PII, intention d'accès non
  autorisé). *Dans le doute : local.*
- si le backend cloud échoue, il **bascule en local** — un tour n'est jamais perdu,
- chaque tour routé porte une **provenance explicite** dans le journal (`routed_to`,
  `routing_reason`, `sensitivity_reasons`) — on peut toujours demander *pourquoi* un tour est parti
  local ou cloud.

Un `PerplexityBackend` (compatible OpenAI) est livré comme premier fournisseur cloud ; l'interface
est enfichable. Activer avec `--cloud` (clé via `PPLX_API_KEY`). **Opt-in — le défaut souverain est
100 % local.**

---

## Console de dev locale (web)

Une petite page web **strictement locale** (stdlib Python, bind `127.0.0.1` — jamais exposée) pour
essayer le modèle + la mémoire dans un navigateur : chatter avec un modèle local, voir **les appels
d'outils mémoire du modèle en direct** (recall / remember + résultats), et basculer `memory-tools` /
injection-recall / cloud.

```bash
python -m multiservice.webchat      # http://127.0.0.1:8765
```

Le champ modèle accepte un nom Ollama **ou un chemin vers un `.gguf`** — les modèles GGUF se
chargent **en process** (`EmbeddedGGUF`, llama-cpp) comme alternative pleinement locale à Ollama.
Tout reste sur ta machine.

---

## La mémoire se cure elle-même

Au fil des mois, le journal accumule doublons, re-logs reformulés et faits périmés. MultiService IA
le garde propre avec une couche de **curation** qui reste constitutionnelle — elle **observe et
propose ; l'humain tranche**. Rien n'est supprimé automatiquement ; corriger = **clôture C3, jamais
suppression**.

- **Détecteurs déterministes** (`curation()` / `multiservice.curation_report`) — lecture seule :
  doublons exacts, quasi-doublons, gabarits non remplis, décisions périmées, contradictions
  candidates, chacun citant ses preuves. Un **rapport quotidien planifié** reste *silencieux tant que
  rien n'est actionnable*.
- **Prévention à la source** — le chemin d'écriture distant (`ingest`) refuse les **valeurs de secret**
  (clés d'API / jetons — un secret dans un journal append-only est ineffaçable), les **gabarits non
  remplis** et les **doublons exacts vivants** (même source + kind + texte), pour que cette pollution
  ne rentre plus (`--force` outrepasse — humain seul, C1).
- **Un comparateur LLM local** (`multiservice.curation_llm`) — un modèle **local** (Ollama, jamais le
  cloud) juge les quasi-doublons / contradictions bruités : il **dé-bruite** les faux positifs et
  propose des **consolidations** (garder le fait existant le plus riche, clore la variante). Il
  **propose, il n'écrit jamais** — chaque proposition est `pending_human` avec sa commande de clôture.

Approuver = une **clôture C3** (`memlog-http … --closes`) : la variante est close, jamais supprimée ;
le canonique reste la vérité courante. La boucle : **détecter → juger (LLM local) → prévenir →
surveiller → l'humain approuve.**

---

## Économie de tokens

Des mesures réelles sur des conversations en production ont montré que jusqu'à **98,5 % des tokens
d'entrée** étaient du ré-envoi de contexte (le « snowball » du contexte qui grossit), et non de
l'information nouvelle. MultiService IA s'attaque à ce gaspillage avec trois leviers compatibles
lecture seule :

- **Cache de résultat exact** — une requête identique est servie sans appeler le modèle (gardé par
  C3 : une correction postérieure invalide l'entrée).
- **Cache sémantique** — une quasi-paraphrase déjà répondue est servie sans le modèle. Décisionnel,
  donc seuil de similarité volontairement haut (« dans le doute, on ne sert pas »).
- **Fenêtrage de contexte** — garde les *N* derniers tours en clair, bornant le snowball.

Le point clé : l'économie n'est pas *promise* — elle est **mesurée**, en lecture seule, par l'outil
`usage()` : combien de tours servis depuis la mémoire, et combien de tokens d'entrée réellement épargnés.

> **Mesure réelle** (un journal réel) : 199 tours · 595 tokens d'entrée épargnés par le fenêtrage ·
> 16 par le cache sémantique (activé récemment). *Tes chiffres dépendront de l'usage — l'important,
> c'est qu'ils soient mesurés, pas affirmés.*

---

## Souveraineté & confidentialité

- Tout tourne **sur ta machine**. Le journal vit dans un fichier local append-only.
- Inférence et embeddings passent par une instance **Ollama locale** — aucune API hébergée.
- Une politique de routage garde le **contenu sensible hors des fournisseurs hébergés** : tout ce qui
  est marqué comme secret/identifiant ou intention d'accès non autorisé n'est jamais routé vers une
  API d'inférence/embedding cloud, et n'est jamais servi par le cache. (Dans le doute : local.)
- **Souveraineté vs réplication.** La phrase ci-dessus concerne le *routage d'inférence*. Le serveur
  central **optionnel** réplique le journal vers un hôte que **tu** contrôles (opt-in, merge
  union-par-id) — pas un tiers ; il ne **filtre pas** sur la sensibilité, mais le chemin d'écriture
  **refuse les valeurs de secret**, donc les credentials n'entrent jamais dans le journal.
- **Ce dépôt n'embarque aucune donnée.** Ton journal est à toi et reste sur ton disque.

---

## Démarrage rapide

Prérequis : Python 3.11+, [Ollama](https://ollama.com) lancé en local.

```bash
# 1. installer
pip install -r requirements.txt

# 2. récupérer un modèle de chat local + un modèle d'embedding
ollama pull <ton-modele-de-chat>   # n'importe quel modèle local ; via OLLAMA_MODEL
ollama pull bge-m3                 # embeddings locaux pour le recall hybride

# 3. chatter (capture automatique ; cache exact + sémantique et fenêtrage ACTIFS par défaut)
python -m multiservice.chat --ollama --recall     # ajoute --recall pour l'injection mémoire en direct

# 4. (re)construire l'index sémantique après avoir chatté
python -m multiservice.index

# 5. lancer les tests
pytest -q
```

La configuration est dans `multiservice/config.py`, surchargeable par variables d'environnement
(`OLLAMA_MODEL`, `EMBED_MODEL`, `JOURNAL_PATH`, `KEEP_TURNS`, …).

---

## Utilisation depuis un client MCP

> **Brancher n'importe quel LLM.** Guide de connexion complet — MCP / REST / fichiers, lecture +
> écriture supervisée, outils, règles de provenance, politique d'écriture, modes — dans
> **[`docs/INTEGRATION.md`](docs/INTEGRATION.md)**.

Lancer le serveur de mémoire en lecture seule :

```bash
python -m multiservice.mcp_server
```

Puis pointer un client compatible MCP dessus. Une config client minimale :

```json
{
  "mcpServers": {
    "multiservice-memory": {
      "command": "/chemin/absolu/vers/python",
      "args": ["-m", "multiservice.mcp_server"],
      "env": { "PYTHONPATH": "/chemin/absolu/vers/ce/depot" }
    }
  }
}
```

> Le serveur met les modules en cache à l'import ; redémarre le client après avoir ajouté un outil.

### Accès distant (serveur HTTP hébergé) — optionnel

> **Optionnel, opt-in.** Par défaut la mémoire est **locale et souveraine** — le serveur stdio
> ci-dessus garde tout sur ta machine et **rien n'exige de serveur**. Centraliser le journal sur un
> VPS ne concerne que ceux qui *veulent* atteindre un journal partagé depuis plusieurs
> machines/réseaux.

Si tu choisis cette option, la même surface en lecture seule est servie en **HTTPS** — un journal
central, aucune copie sur les clients (les données restent sur un hôte que *tu* contrôles). Lancer le
point d'entrée streamable-HTTP (derrière un reverse proxy qui termine le TLS et authentifie) :

```bash
multiservice-mcp-http   # outils lecture seule en streamable-HTTP (défaut 0.0.0.0:8302)
```

La protection anti-DNS-rebinding reste **active** : déclarer le(s) Host public(s) servi(s) via
`MULTISERVICE_HTTP_ALLOWED_HOSTS` (séparés par des virgules, ex. `mem.example.com`). Le placer
derrière un reverse proxy ajoutant TLS + bearer token + allowlist IP, puis brancher n'importe quel
poste :

```bash
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp \
  --header "Authorization: Bearer <token>"
```

Une recette prête à l'emploi (Docker avec le journal monté en **lecture seule** + nginx) est dans
[`deploy/`](deploy/).

> **Le sémantique est local ; un central sans GPU reste lexical.** Les embeddings (`bge-m3`) sont
> calculés sur la machine qui a le GPU — ton poste. Un serveur central sans GPU sert la surface
> lecture seule en recall **lexical** (toujours sourcé, daté, conscient du C3) ; le recall
> *sémantique* hybride est une capacité locale. C'est voulu : le chemin souverain est local, et le
> serveur central est une **option** pour atteindre un journal partagé — pas une exigence, et ce
> n'est pas là que tourne le modèle.

**Écriture distante authentifiée (ingest).** Les postes distants peuvent aussi *écrire* dans le
journal central via **mTLS + HMAC** (anti-rejeu nonce + horodatage) ; la source est **imposée côté
serveur** depuis le CN du certificat client — impossible de l'usurper. Commande client : `memlog-http`.
Recette dans [`deploy/`](deploy/) (`Dockerfile.ingest`, `gen-mtls.sh`).

**API REST web (pour les LLM web).** Une surface REST séparée, **publique et authentifiée par token**,
permet aux assistants web (ChatGPT / Custom GPT, connecteurs) de lire et écrire la mémoire centrale :
`GET /recall`, `POST /remember`, `GET /recent`, plus un schéma **OpenAPI** auto (`/openapi.json`) pour
les GPT Actions. Le token bearer de chaque client est mappé à une source (imposée serveur). Central
uniquement, rate-limité. Recette dans [`deploy/`](deploy/) (`Dockerfile.webapi`) et
[`deploy/SETUP-POSTE-CLIENT.md`](deploy/SETUP-POSTE-CLIENT.md).

---

## CLI

```bash
python -m multiservice.chat        # boucle de chat (capture + journalise chaque tour)
python -m multiservice.chat --memory-tools --cloud   # mémoire agentique + routage cloud optionnel
python -m multiservice.webchat     # console web locale (Ollama/GGUF + activité mémoire en direct)
python -m multiservice.inspect     # observabilité d'usage (lecture seule)
python -m multiservice.economy     # comptabilité de tokens : ré-envoi de préfixe, économie fenêtrage
python -m multiservice.index       # (ré)indexation incrémentale des embeddings locaux
python -m multiservice.maintenance # réindexation incrémentale, planifiable (garde l'index frais)
python -m multiservice.curation_report  # rapport de santé de curation quotidien (déterministe, lecture seule)
python -m multiservice.curation_llm     # revue LLM locale : dé-bruitage + propositions de consolidation
python -m multiservice.curation_inbox   # inbox web locale : approuver/rejeter les propositions en un clic
python -m multiservice.preheat     # pré-chauffage : coût projeté du prochain tour
python -m multiservice.mcp_server  # serveur MCP de mémoire (lecture seule)
python -m multiservice.projlog "<décision>" --kind decision --session <sujet>   # journaliser une décision projet
```

Dans la boucle de chat : `/correct <note>`, `/note <texte>`, `/model <nom|chemin.gguf>`, `/reset`, `/quit`.

> **Garder l'index frais, automatiquement.** `multiservice.maintenance` ne réindexe que ce qui a
> changé et est prévu pour être planifié (tâche planifiée Windows / cron), pour que le recall hybride
> reste frais sans étape manuelle. Les embeddings sémantiques sont une capacité **locale (GPU)** —
> voir la note sous *Accès distant* sur pourquoi un central sans GPU reste lexical.

> **Dogfooding.** `projlog` inscrit les décisions/corrections du projet dans le journal, pour que
> `recall`/`brief`/`recent` ancrent le travail futur dans le raisonnement passé — la mémoire se
> souvient de son propre développement. C'est une capture (append-only) ; la surface MCP reste en
> lecture seule.

---

## État du projet

Moteur fonctionnel avec une surface de mémoire complète en lecture seule, **mémoire agentique** (le
modèle cherche et écrit son propre namespace `project:ollama`, gardé), **routage multi-fournisseurs
local d'abord** (cloud Perplexity optionnel derrière une politique « sensible → local »), une
**console web locale** (Ollama + GGUF), cache exact + sémantique, fenêtrage de contexte, ébauche de
skills émergentes, sauvegarde append-only avec manifestes SHA-256, recall hybride local,
**réindexation planifiable**, et une couche **auto-curative** (détecteurs déterministes + rapport
planifié, gardes dédup/gabarit à l'ingest, et un comparateur LLM local qui dé-bruite et propose des
consolidations — le tout validé par l'humain, C3). Tout tourne **localement par défaut** ; le serveur
central hébergé (HTTP lecture + ingest mTLS + API REST web) est une **option opt-in** pour partager
un journal entre machines. **Couvert par une suite pytest croissante (actuellement verte).** Chaque
fonctionnalité laisse un test de régression permanent ; tout problème révélé par l'usage réel
devient un test.

---

## Feuille de route

- ✅ **Routage multi-fournisseurs** — livré : backend cloud optionnel (Perplexity) derrière la même
  interface, gouverné par la politique « sensible → local seul », avec provenance de routage explicite.
- ✅ **Mémoire agentique** — livrée : le modèle local pilote lui-même les outils mémoire et peut écrire
  dans un namespace gardé, non-autoritatif `project:ollama` ; les outils mémoire restent local-only.
- ✅ **Console web locale** — livrée : `multiservice.webchat`, Ollama/GGUF + activité mémoire en direct.
- ✅ **Réindexation planifiable** — livrée : `multiservice.maintenance`, incrémentale, garde le recall frais.
- ✅ **Mémoire auto-curative** — livrée : détecteurs déterministes + rapport planifié, gardes à l'ingest
  (dédup exact + gabarit non rempli), et un comparateur LLM local (dé-bruitage + consolidations),
  le tout validé par l'humain (clôture C3, jamais suppression).
- ✅ **Une seconde surface (hébergée) en lecture seule** — livrée : serveur streamable-HTTP, voir [`deploy/`](deploy/).
- ✅ **Écriture distante authentifiée (ingest)** — livrée : mTLS + HMAC + anti-rejeu, client `memlog-http`.
- ✅ **API REST web pour les LLM web** — livrée : FastAPI publique authentifiée par token
  (recall/remember/recent + OpenAPI), prête pour les Custom GPT. Voir [`deploy/`](deploy/).
- ✅ **Revue de projet (rôle Synthèse)** — livrée : `project_review(project)` reconstruit l'état
  bi-temporel d'un projet (décisions valides vs corrigées avec le *pourquoi*, hypothèses, validations, leçons).
- ✅ **Garde anti-secret à l'écriture** — livrée : le chemin d'écriture refuse les valeurs de credential
  (un secret dans un journal append-only est ineffaçable) ; `--force` outrepasse (humain, C1).
- ✅ **Guide d'intégration** — livré : [`docs/INTEGRATION.md`](docs/INTEGRATION.md) — brancher n'importe
  quel LLM (MCP / REST / fichiers, lecture + écriture supervisée).

### À venir

- **Chiffrement au repos** du journal local (append-only + chiffrement — un chantier délibéré).
- **Durcissement multi-nœuds** — révocation de certificat par client et rate-limiting.
- **Passage à l'échelle** pour de très gros journaux au long cours — stockage indexé / paginé (back-end graphe optionnel).
- **Calibrage du comparateur** — honorer les rejets, ignorer les variantes versionnées / de lieu distinct.

---

## Filiation de conception

Les principes constitutionnels (provenance obligatoire, clôture bi-temporelle jamais-suppression,
humain dans la boucle) sont hérités d'un système compagnon d'event sourcing bi-temporel et appliqués
ici aux échanges LLM. Il en résulte une mémoire fidèle par la capture et fiable par construction.

---

## Licence

**Apache License 2.0** — voir [`LICENSE`](LICENSE) et [`NOTICE`](NOTICE). Permissive (libre, y
compris en usage commercial), avec octroi de brevet explicite. © 2026 MultiService IA authors.

---

## Une note sur tes données

MultiService IA est conçu pour que ton historique de conversation ne quitte jamais ton contrôle. Le
code de ce dépôt décrit le *système*, pas ta mémoire : aucun contenu de journal n'est inclus, et
aucun ne devrait être committé. Garde tes journaux `*.jsonl` hors du gestionnaire de versions
(ajoute-les au `.gitignore`).
