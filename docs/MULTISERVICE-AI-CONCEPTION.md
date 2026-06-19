# MultiService AI — Conception technique

> Le « comment ». À lire après `MULTISERVICE-AI-VISION.md` ; décisions dans `DECISIONS.md`.
> Principe directeur conservé : **tout module est pur — `List[AetherEvent] → résultat`** ;
> seule exception sanctionnée = les backends d'inférence (§10).
> Daté : 16 juin 2026. Statut : cadre figé, seuils à calibrer.

---

## 1. Vue d'ensemble (3 couches)

```
┌──────────────────────────────────────────────────────────────────────┐
│  SURFACES — connexion model-agnostic, sans API propriétaire            │
│   • Routeur API        → apps/scripts/agents  (bénéfice complet)       │
│   • Serveur MCP        → Claude.ai / ChatGPT.com (accès mémoire/skills)│
│       resources (lecture seule) · tools (recall/why/economy) · prompts │
└───────────────┬──────────────────────────────────────┬─────────────────┘
        observe (capture)                       restitue (serve)
┌───────────────▼──────────────────────────────────────▼─────────────────┐
│  PLAN DE CONTEXTE + ROUTEUR (nouveau) — logique pure, sans état mutable │
│   generate() : capture → recall → composition → cache → backend → cap.  │
│   backends (effet de bord, §10) : EmbeddedGGUF · Claude · ChatGPT       │
│   economy : tokens, redondance, cache · skills : cristallisation        │
│   predict : pré-chauffage / estimation (LECTURE SEULE)                  │
└───────────────┬──────────────────────────────────────────────────────────┘
        réemploi (tel quel, ou détecteurs « tournés vers l'avant »)
┌───────────────▼──────────────────────────────────────────────────────────┐
│  AETHERCORE EXISTANT — substrat souverain (C1-C6)                         │
│   events · twin · memoria(Neo4j) · insights · predict · shield · briefing │
│   journal-vérité append-only  ~/.aethercore/journal.jsonl                 │
└────────────────────────────────────────────────────────────────────────────┘
```

Le Plan de Contexte **n'introduit aucune écriture nouvelle dans le journal autre que des
événements de capture** (datés, sourcés). Il ne mute rien. Test structurel garant (§10/11).

---

## 2. Le routeur multi-fournisseurs (cœur de « MultiService AI »)

Une seule interface, des backends interchangeables. La logique de décision est **pure**
(`List[AetherEvent] → plan de tour`) ; seuls les backends touchent le réseau / le modèle.

```python
class Backend(Protocol):
    def generate(self, composed_prompt, params) -> Completion: ...
    @property
    def count_source(self) -> str: ...   # 'local_tokenizer' | 'provider_usage'

# backends figés :
#   EmbeddedGGUF(model_path: str)   # n'importe quel .gguf, in-process, souverain
#   Claude(model_id)                # API
#   ChatGPT(model_id)               # API
```

Pipeline d'un tour, identique quel que soit le backend :

```
capture(prompt) → recall(top-k, bi-temporel) → compose(préfixe + delta, clôture C3)
   → cache_check(result-cache) → [backend.generate() si miss] → capture(completion,
   token_usage, context_injection) → détecteurs (hors chemin critique)
```

**Politique de routage (souveraineté).** Une règle pure décide du backend : `sensible →
EmbeddedGGUF (local seul)` ; sinon → cloud au choix. « Sensible » est un prédicat sur
l'événement (provenance, tags), pas une heuristique LLM.

---

## 3. Schéma d'événements (extension, pas nouveau schéma)

On réutilise `AetherEvent` (C2/C3 portés par le type ; `EventType` est un enum, l'étendre
est trivial). Nouveaux types/sources, aucune rupture :

| Type | Source (C2) | Rôle | Notes C3 |
|---|---|---|---|
| `prompt` | `user/llm` | ce que l'humain a demandé | valid-time = instant du tour |
| `completion` | `llm` | réponse du modèle | porte `model_id` + backend |
| `tool_call` | `agent` | action demandée | corrélé à un `tool_result` |
| `tool_result` | `agent` | résultat / erreur | *traceback* précieuse à capturer |
| `correction` | `user` | l'humain corrige | **clôture** une croyance (C3) ; **borne de tâche** |
| `token_usage` | `meter` | comptage du tour | `model_id` + `tokenizer` + **`count_source`** (§7) |
| `context_injection` | `plane` | chaque bloc servi, avec sa raison | rend l'injection auditable |
| `skill_candidate` | `plane` | pattern proposé comme skill | `type=suggestion` ; porte sa `source` (observé vs proposé-LLM) + provenance set |

**Deux innovations de schéma :**

- **`context_injection`** : on journalise *ce qu'on injecte et pourquoi* → audit « qu'a vu
  l'agent et pourquoi » (replay, §5) + **ROI d'injection** (a-t-il changé la sortie ?).
- **`correction`** : signal d'apprentissage le plus riche. Clôture C3 + borne de tâche.

---

## 4. Carte de réemploi — pourquoi ce n'est pas une réécriture

Chaque capacité LLM réutilise un module existant. `[neuf]` / `[adapté]` = vérifié sur le source réel.

| Module existant | Réemploi |
|---|---|
| `events.py` (`AetherEvent`, C2/C3) | nouveaux types (§3) ; schéma inchangé |
| `twin.py` (diff, anti-bruit) | **diff de contexte** entre tours ; anti-bruit = ne pas réinjecter l'inchangé |
| `memory/memoria.py` (`recall`/`why`, bi-temporel) | `recall` tel quel ; `recall(as_of=…)` = reconstruction d'état (tel quel) ; `why` **`[adapté]`** *par entité* ; replay event→cause **`[neuf]`** (S18) |
| `insights.py` (5 détecteurs) | gaspillage : SPOF-contexte, fenêtre muette, pic, flapper (tels quels) ; **rafale=tâche `[neuf]`** (§6) |
| `predict.py` (N0, lecture seule) | **pré-chauffage** + estimation de coût. *Patron de référence du Plan de Contexte.* |
| `shield.py` (N1, observe/alerte) | **garde-fou tokens** : alerte « tour coûteux » ; observe, n'empêche pas |
| `experience.py` (incidents clos, `1−0.5^n`) | **cristallisation de skills** : même courbe, déjà testée |
| `briefing.py` | **briefing d'usage LLM** : tokens, % gaspillé, skills, contexte chaud |
| `cli.py` (`memoria`) | nouveaux verbes : `serve`, `route`, `economy`, `skills`, `replay` |

> 4 des 5 détecteurs se tournent juste vers le contexte ; le 5e (rafale=tâche) et le replay
> plein sont le seul vrai neuf.

---

## 5. Les 5 détecteurs `insights`, relus pour le contexte

| Détecteur infra | Version « contexte LLM » | Action proposée (jamais imposée) |
|---|---|---|
| **SPOF** (in-degree, ex. *poste, 325 deps*) | bloc dont **tout** dépend, réinjecté chaque tour | → **cacher** (si le modèle/pile le permet) ou **résumer en skill** |
| **fenêtre muette** | contexte présent mais **jamais relu/cité** | → le **retirer** (gaspillage pur) |
| **pic** | tour exceptionnellement coûteux | → **compacter** / clôturer (C3) |
| **flapper** | demande qui **oscille** | → **clarifier** ou proposer une **skill** |
| **déploiement** `detect_deployments` (D1) | **inspiration**, pas réemploi : D1 trop spécifique | → **`[neuf]`** détecteur de rafale `tool_call`/`tool_result` = unité « tâche » |

**Définition de « tâche » (figée, défi n°7).** Priorité : id de session/trace si exposé.
Repli **de première classe** (le sidecar/backend n'expose pas toujours d'id uniforme) :
**fenêtre temporelle + corrélation** de rafale. Une `correction` borne une sous-tâche.

Leçon BITS : **calibrer sur le réel observé**. D'où Sprint 13 = capture seule.

---

## 6. La surface MCP (lecture seule = conforme à la constitution)

```
resources/   (LECTURE SEULE)
  aether://recall/{entity}        contexte pertinent, provenance attachée
  aether://why/{entity}           historique d'une entité (PAR ENTITÉ — état réel du code)
  aether://briefing/today         briefing d'usage du jour

tools/       (lecture/suggestion — jamais de mutation du journal)
  recall(query, k)                top-k pertinent
  economy(scope)                  tokens dépensés, % redondant, candidats cache
  why(entity_uid)                 historique bi-temporel d'une entité
  replay(event_id)                [NEUF, S18] chaîne causale event → contexte vu
  propose_skill(pattern)          émet un skill_candidate (suggestion, quarantaine v1)

prompts/     (gabarits = skills)
  skill:{name}                    SKILL.md promu, versionné, bi-temporel
```

Point constitutionnel : **aucun tool MCP n'écrit un fait dans le journal.** `propose_skill`
n'émet qu'une suggestion **et, en v1, n'alimente que la file en quarantaine** (cristallisation
v1 = observé seul). La capture se fait par le **routeur/backend** ou un *hook* client, jamais
par un tool que le LLM déclenche (sinon le LLM contrôlerait ce qui est mémorisé — interdit).

---

## 7. Le backend local : GGUF embarqué in-process (figé)

Pas de daemon, pas de proxy. `llama-cpp-python` charge **n'importe quel `.gguf`** en process :

```python
from llama_cpp import Llama, LlamaDiskCache
llm = Llama(model_path="…/modele.gguf", n_ctx=…)
llm.set_cache(LlamaDiskCache(…))   # persistant entre redémarrages
```

- **Model-agnostic** : aucun modèle figé ; Gemma 4 12B n'est qu'un exemple.
- **Tokenisation in-process** → le défi n°3 *local* disparaît (le modèle compte lui-même).
- **Zéro réseau** → (c) au sens le plus dur.

**Réutilisation KV de préfixe : ne PAS s'y fier (figé, D6/D7).** `llama-cpp-python` détecte
le plus long préfixe commun (`LlamaRAMCache`/`LlamaDiskCache`, log « cache hit/miss »), **mais
ça dépend du modèle chargé.** Pour Gemma 4 (SWA + KV partagé), llama.cpp **re-traite le prompt
entier** → pas de réutilisation. Donc :

- **Bonus opportuniste** seulement : GGUF dense sans fenêtre glissante.
- **Économie locale réelle = §8** (result-cache + clôture C3), indépendante de l'architecture.
- À vérifier sur ta **build/quant exacte** (issues ouvertes).

---

## 8. Comptabilité de tokens (`economy`) — hétérogène mais honnête (défi n°3)

- **API distante** : lire l'`usage` retourné. `count_source = provider_usage`. Compte le facturé.
- **Local GGUF** : le runtime compte ; `cache_hit` (si le modèle le supporte) donne cached
  vs fresh. `count_source = local_tokenizer`.
- Chaque tour → un `token_usage` portant `model_id` + `tokenizer` + **`count_source`**.
- **Règle gravée** : `economy` agrège **par `(model_id, count_source)`** et **ne somme jamais**
  à travers des bases. Un compte facturé-cloud et un compte tokenizer-local ne sont montrés
  que **côte à côte**. La part redondante (% gaspillé) est **intra-trace, intra-modèle**.
- Dérive : tokens/tour, tokens/**tâche** (§5), part redondante, gain cache → briefing.

> **Optimiser tokens/tour est un leurre** ; la bonne unité est **tokens/tâche** (50-200
> appels/tâche). D'où la définition de « tâche » (§5).

---

## 9. Cache, recall, stockage

**Cache de résultat (le gros gain, figé D8).** Clé = `hash(prompt) + empreinte de
provenance`. **Toute clôture (`valid_to`) d'un fait contribuant invalide l'entrée** → seul
cache C3-correct (jamais une réponse dont la base a été clôturée). Exact d'abord, sémantique
ensuite.

**Recall hybride (figé D14).** `recall` est aujourd'hui **purement lexical** (`CONTAINS`) —
rien à casser. Le vectoriel est **additif et suggestif** : filtre bi-temporel Neo4j
**décisionnel** + ré-ordonnancement par **embedding LOCAL** (sentence-transformer embarqué,
jamais d'API hébergée — sinon (c) tombe au moment où l'on vectorise).

**Stockage / échelle (ouvert).** Tiering chaud/tiède/froid (clôture ≠ suppression → froid
rejouable). `jsonl` reste la vérité ; Neo4j = miroir interrogeable swappable (`Protocol`),
partitionnable par fenêtre temporelle si le volume LLM le force.

---

## 10. Point d'inflexion : les backends = unique dérogation à la pureté (figé D15)

Aucune inférence n'était câblée dans AetherCore ; tout est `List[AetherEvent] → résultat`.
Les **backends d'inférence** (`EmbeddedGGUF`, `Claude`, `ChatGPT`) sont la **PREMIÈRE pièce
à effet de bord** (I/O modèle/réseau). On grave l'exception **une fois** :

- **logique de routage et de composition** : **pure et testable** (recall, préfixe, choix de
  cache, clôture C3, politique « sensible→local ») — tout en `List[AetherEvent] → résultat` ;
- **coquille I/O** (`backend.generate()`) : **isolée** au bord, derrière le `Protocol` ;
- **test structurel** (façon grep-test `predict.py`) : le cœur ne contient pas d'I/O et
  n'écrit aucun fait hors capture.

Mieux nommer l'exception que la laisser s'éroder tour après tour.

---

## 11. Conventions héritées à respecter

- **Sorties console ASCII** (S10-F3, S11-F3) ; les `.md` gardent les accents.
- **`predict` reste en lecture seule** ; le Plan de Contexte aussi (test structurel obligatoire).
- **Chaque sprint laisse un test de régression.**
- **Piège bac à sable** : le montage Linux tronque les fichiers fraîchement édités. Ne pas
  `git commit` depuis le bac à sable ; committer côté Windows.
- **Tout module pur** sauf les backends (§10) ; leur logique de décision reste pure.
