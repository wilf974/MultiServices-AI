# MultiService AI — Vision (doc de cadrage)

> Pivot d'AetherCore : du jumeau numérique de l'**infrastructure** vers un
> **substrat de mémoire et de contexte souverain pour LLM/agents**, exposé par une
> **couche routeur multi-fournisseurs** (le projet **MultiService AI**).
> Le substrat reste **AetherCore** ; MultiService AI = la couche par-dessus (routeur +
> Plan de Contexte). Composant architectural du substrat : *le Plan de Contexte*.
> Statut : **cadre figé le 16 juin 2026** (voir `DECISIONS.md`) ; seuils à calibrer sur le réel.
> À lire avec `MULTISERVICE-AI-CONCEPTION.md`, `MULTISERVICE-AI-FEUILLE-DE-ROUTE.md`, `DECISIONS.md`.

---

## 1. La thèse en une phrase

> Tu as déjà construit le moteur. Tu veux juste **changer ce qu'il observe.**

AetherCore observe une infra (un poste Windows, une VM, des conteneurs), mémorise chaque
fait comme `AetherEvent` daté/sourcé/bi-temporel, le restitue (`recall`/`why`), le
contextualise (Predict N0) et l'expose (briefing) — **sans jamais agir.**

MultiService AI applique **exactement le même moteur** à un nouveau flux : **tes échanges
avec les LLM/agents**, quel que soit le fournisseur. Chaque prompt, réponse, appel d'outil
et correction devient un `AetherEvent`. À partir de là, le substrat :

- **mémorise** ce qui a déjà été demandé/fait → tu ne le ré-expliques plus (économie) ;
- **restitue** le bon contexte au bon moment au LLM (au lieu de tout empiler) ;
- **détecte** le gaspillage (contexte ré-injecté, jamais relu, demande qui oscille) ;
- **cristallise** des *skills* à partir des patterns réels — proposées, jamais imposées ;
- **anticipe** le contexte du prochain tour (Predict tourné vers l'avant) ;
- **expose** tout ça dans un briefing d'usage : tokens dépensés, % gaspillé, skills
  proposées, contexte « chaud ».

**La preuve que ce n'est pas un pari, mais une répétition** : `predict.py` (Sprint 12)
a *déjà* fait ce mouvement — il prend `detect_spof` et `detect_blind_windows` d'`insights.py`
et les **tourne vers l'avant**, sous un contrat lecture-seule gravé, vérifié par un test
structurel qui *grep le source* (`test_le_module_ne_contient_aucun_pouvoir_d_action`).
Le « Plan de Contexte observe/restitue/jamais ne mute » se copie, ne s'invente pas.

Le mantra existant se prolonge sans rupture :

> **Le Plan observe · la Mémoire restitue · le LLM raisonne · l'Humain tranche.**
> (et le LLM peut trancher *sous contrainte* — jamais muter le journal.)

---

## 2. Le principe directeur : « une force, pas une dépendance »

Ta phrase : *« mon IA ne doit pas dépendre de l'agent ou du LLM, mais doit être une force
pour le LLM. »* C'est l'axe central. Conséquences d'architecture :

1. **Le substrat est souverain.** Le journal-vérité (`~/.aethercore/journal.jsonl`,
   append-only, C1-C6) **survit à n'importe quel LLM.** On débranche Claude, on branche un
   GGUF local, puis ChatGPT : la mémoire persiste et continue d'apprendre. Le LLM est un
   *consommateur* du substrat, pas son propriétaire. (Confirmé : `memoria` parle à un
   `GraphBackend` *swappable* via `Protocol` ; aucune inférence n'est câblée.)

2. **Le LLM ne peut pas corrompre sa propre mémoire.** Contrairement aux frameworks où
   l'agent gère sa mémoire (il garde, édite, efface), MultiService AI **interdit l'écriture
   arbitraire et la suppression** (C3 : clôture, jamais suppression). Le LLM *lit* et
   *suggère* ; il ne réécrit pas l'histoire. **Mémoire que le LLM ne peut pas se mentir.**

3. **Le substrat est 100 % local (figé : (a)+(c)).** La mémoire ne sort **jamais** de ta
   machine. L'inférence reste locale par défaut (GGUF in-process) ; le cloud est un *choix
   par tour* (voir §5). Aucune dépendance à une API propriétaire au cœur.

C'est la discipline d'AetherShield (« observe et alerte, JAMAIS n'agit ») et de Predict N0
(« estime, contextualise, cite — ne décide pas ») appliquée au domaine LLM. La séparation
que tu protèges « à tout prix » devient le cœur du produit.

---

## 3. Pourquoi c'est innovant (honnêtement)

Le domaine 2026 est dense. **La mémoire pour LLM, l'apprentissage de skills,
l'auto-amélioration et le cache de tokens existent déjà.** Ce qui est neuf ici n'est pas
une brique — c'est une **combinaison sous discipline constitutionnelle** que personne
n'assemble :

### Le paysage (état 2026, pour situer)

| Solution | Modèle | Faille reconnue |
|---|---|---|
| **mem0** | extraction de faits → base vectorielle, drop-in | personnalisation surtout ; gouvernance/lignée absente ; graphe payant |
| **Zep / Graphiti** | graphe de connaissances *temporel* | fort en temporel, mais features avancées cloud-only |
| **Letta / MemGPT** | l'**agent gère sa propre mémoire** | « toute opération mémoire passe par le LLM → opacité » (l'agent peut biaiser sa mémoire) |
| **Cognee / autres** | multi-stratégie de retrieval | orienté retrieval, pas observabilité d'usage |

Constat récurrent 2026 : ces frameworks **manquent de gouvernance** — pas de provenance,
pas de lignée, pas de bi-temporalité auditable. C'est le terrain où AetherCore est fort.

### Les 5 différenciateurs

1. **Gouvernance native.** Provenance obligatoire (C2), bi-temporalité (C3), journal
   append-only. → *mémoire auditable et rejouable.*
2. **Non-corruptible par le LLM (l'anti-Letta).** Le LLM lit et suggère ; il ne mute pas.
   La promotion est **décidée par l'humain**. → *« force, pas dépendance » littérale.*
3. **Souverain et local-first.** Substrat 100 % local ; inférence locale possible (GGUF
   in-process). → *vie privée + indépendance vendeur.*
4. **Unifié, pas mono-fonction.** Mémoire **+** `insights` **+** `predict` **+** comptabilité
   de tokens **+** skills émergentes — *tout comme `AetherEvent`, donc mesurable et traçable.*
   Les autres font « la mémoire » ; toi, « l'observabilité de ton propre usage LLM. »
5. **Reconstruction bi-temporelle du contexte (superpouvoir C3).** Reconstituer ce que
   l'agent voyait à T, et ce que tu *croyais* alors vs aujourd'hui.
   **Précision honnête (correction du code)** : `memoria.recall(as_of=…)` donne déjà la
   *reconstruction d'état* à T (gratuit). Mais la traversée *événement → chaîne causale*
   (replay plein) n'existe pas — `memoria.why` est *par entité*, pas par event_id. Le replay
   est du **neuf à écrire** → Sprint 18, pas un réemploi gratuit.

> Les idées existent ; **la discipline qui les rend dignes de confiance, non.** AetherCore
> *est* cette discipline.

---

## 4. L'économie de tokens, concrètement (ton objectif n°1)

Le réel 2026 : **40 à 60 % des tokens d'entrée sont du contexte inutile**. On paie deux
fois : facture **et** latence. Les agents font 50-200 appels par tâche → un token « pas
cher » fait une **tâche chère.**

**Vérité dure, model-agnostic (figé) :** l'économie locale **ne repose pas** sur la
réutilisation KV de préfixe — elle dépend du modèle GGUF chargé, et des modèles à fenêtre
glissante (SWA) comme **Gemma 4 forcent llama.cpp à re-traiter le prompt entier** (pas de
réutilisation KV) — *à vérifier sur ta build/quant exacte, ce sont des issues ouvertes (D7)*.
Les deux leviers **indépendants de l'architecture** portent donc l'économie locale :

1. **Cache de résultat** (le plus gros gain) : question déjà répondue → servir depuis le
   journal, **ne pas appeler le modèle.** Seul cache qui économise *aussi la sortie*, et il
   se fiche du SWA. Garde C3 obligatoire (cf. `DECISIONS.md` D8).
2. **Clôture C3 agressive** (« ne pas remplir ») : un prompt court coûte directement moins
   cher si le modèle re-traite tout. Ce n'est plus une optimisation parmi d'autres — c'est
   *la* défense locale.

Leviers **opportunistes** (bonus quand la pile/le modèle le permet) :

| # | Mécanique | Réemploi | Quand ça paie |
|---|---|---|---|
| 3 | **Préfixe stable / réutilisation KV** | discipline anti-bruit de `twin.py` | GGUF **dense** sans SWA ; **API cloud** (Claude/ChatGPT cachent le préfixe) |
| 4 | **Recall sélectif** (top-k pertinent) | `memoria recall` (lexical → hybride) | toujours : tape dans les 40-60 % gaspillés |
| 5 | **Substitution par skill** (~50 tokens vs ~2000) | `experience.py` + skills | explication récurrente |
| 6 | **Détection de gaspillage** (SPOF-contexte, fenêtre muette, pic, flapper) | 4 des 5 détecteurs d'`insights.py` | rend le gaspillage *visible* |
| 7 | **Pré-chauffage** (anticiper le prochain tour) | `predict.py` (lecture seule) | économise des appels entiers |

**Ironie utile** : le cloud n'est pas que « plus intelligent » — c'est aussi **là où le
levier d'entrée marche** (prompt-caching API), pendant que Gemma le refuse en local. Le
routeur peut donc envoyer le prefix-heavy vers le cloud.

> **La rigueur, c'est la différenciation** : le briefing rapporte *« X tokens ce jour,
> Y % redondant, voici la skill qui aurait économisé Z. »* Observabilité de ta conso LLM.

---

## 5. L'architecture « MultiService » : un routeur souverain (figé)

« Sans API » = **(a)** pas de lock vendeur **et (c)** zéro réseau pour la mémoire. La
réponse est un **routeur multi-fournisseurs** : une interface `generate()`, des backends
interchangeables, tous enveloppés par le substrat (capture → recall → composition → cache →
backend → capture).

```
        app / script / agent              Claude.ai / ChatGPT.com
              │ (API)                            │ (MCP)
              ▼                                  ▼
   ┌─────────────────────────  ROUTEUR  ─────────────────────────┐
   │   substrat : capture → recall → composition → cache         │
   │            ┌───────────────┬───────────────┬──────────────┐ │
   │  backends: │ EmbeddedGGUF  │    Claude      │   ChatGPT    │ │
   │            │ (in-process,  │    (API)       │   (API)      │ │
   │            │  souverain)   │                │              │ │
   │            └───────────────┴───────────────┴──────────────┘ │
   └──────────────────────────────────────────────────────────────┘
            même mémoire · mêmes skills · même comptabilité
```

- **`EmbeddedGGUF`** — **GGUF embarqué in-process** via `llama-cpp-python`
  (`Llama(model_path=…)`). **Model-agnostic** : charge *n'importe quel* `.gguf` (pas de
  modèle figé). Tokenise lui-même, cache `LlamaRAMCache`/`LlamaDiskCache`, **zéro réseau** —
  (c) au sens le plus dur. Pas de daemon Ollama, pas de proxy.
- **`Claude` / `ChatGPT`** — backends API. Bénéficient de la même mémoire/skills/compta, et
  leur prompt-caching cloud *fonctionne* (cf. §4).
- **Standards ouverts** : **MCP** (resources lecture seule, tools recall/why/economy,
  prompts=skills) et **Agent Skills** (`SKILL.md` portable, progressive disclosure).

**Deux surfaces (figé : les deux) :**

1. **Routeur API** — tes apps appellent ton endpoint → **bénéfice complet** (capture +
   injection + économie + skills).
2. **Serveur MCP** — Claude.ai / ChatGPT.com tirent mémoire+skills en lecture. Honnête :
   **accès mémoire oui, économie non** (tu ne contrôles pas leur prompt ; capture partielle,
   seulement ce qui passe par les tools MCP).

**Politique de souveraineté (la « force, pas dépendance » concrète) :** local GGUF = 100 %
privé (rien ne sort) ; cloud = ce tour-là sort de ta machine. Règle du routeur :
**« sensible → local seulement »**, le reste → cloud au choix. Le substrat est la constante ;
les modèles sont des consommateurs interchangeables.

> **Topologie (tranché — couplage assumé)** : Gemma (~16 Go VRAM) tourne sur le **Poste
> Windows** (GPU local). Conséquence honnête : l'inférence **repose sur le SPOF (325 deps)
> que ton propre Shield surveille** — si le poste tombe, l'inférence locale tombe avec lui.
> C'est un choix accepté (simplicité) ; mitigation possible plus tard (passthrough VM, ou
> faire survivre le substrat hors-poste). Documenté, pas caché.

---

## 6. L'apprentissage et les skills

MultiService AI apprend de **deux flux** : ce que *tu* demandes (prompts, corrections,
préférences) et ce que le *LLM/agent fait* (réponses, outils, résultats, erreurs) :

- **patterns de requêtes récurrents** → candidates *skills* ;
- **besoins de contexte récurrents** → candidats pré-chauffage / cache ;
- **corrections répétées** → mémoire de préférences (une correction *clôture* une croyance —
  C3 pur — et **borne une tâche**) ;
- **points chauds de tokens** → où le contexte est gaspillé ;
- **rafales d'appels d'outils corrélés** → une *tâche*. **Correction du code** : ce n'est
  PAS `detect_deployments` (D1, trop spécifique : app + ≥2 services/minute via DEPENDS_ON).
  Il faut un **nouveau** détecteur de rafale `tool_call`/`tool_result` (esprit transféré,
  code non).

**Skills émergentes, promues par l'humain (règles figées) :**

- **v1 = cristallisation sur l'OBSERVÉ seul.** Aucune candidate proposée par le LLM au
  départ ; elles arrivent plus tard, en **quarantaine séparée**.
- **Séparation par `source` (C2)** : observé vs proposé-LLM — un prompt malveillant ne se
  déguise pas en usage observé.
- **La provenance relève la barre, pas la porte.** L'observé est *aussi* manipulable
  (répéter exprès) → quota + dédup + seuil `1−0.5^n` (`experience.py`, déjà testé), **et**
  promotion humaine comme dernier rempart.
- **Skill bi-temporelle (C3)** : clôture (`valid_to`), jamais suppression. 3 signaux de
  péremption : fenêtre muette sur le déclencheur, **pic de corrections** (`detect_volume_spikes`
  nourri d'événements **filtrés sur les `correction`** — un pic de volume général ≠ un pic de
  corrections), **rétrécissement de la preuve** (provenance set clôturé). L'humain
  revoit/clôt/rafraîchit.

> Gravé, **leçon BITS** : ne **jamais** cristalliser sur du bruit. Calibrer après le réel.

### Cohérence constitutionnelle : N2 et la promotion de skills, *même* patron

L'autonomie N2 côté infra (« gagnée, mesurée par l'Experience Engine, autorisée playbook
par playbook, réversible, coupe-circuit, audit, jamais sur un détecteur à faux positifs »)
est **mot pour mot** la règle de cristallisation des skills. L'**Experience Engine** est la
**porte de confiance commune** aux deux domaines. La constitution généralise — bon signe.
(Voir le doc N2 pour « réversible = y compris ses conséquences » et le **mode ombre** : un
playbook qui journalise « j'AURAIS agi » sans rien faire, pour mesurer le passé du *playbook*
avant de l'armer — la discipline BITS appliquée à l'autonomie elle-même.)

---

## 7. Options de fonctionnalités (menu à arbitrer)

- **A. Garde-fou tokens (style Shield N1).** Alerte avant un tour coûteux/redondant.
  Observe, **n'empêche pas.**
- **B. Replay / debug bi-temporel.** **Neuf (event → chaîne causale) → Sprint 18.**
- **C. Portabilité inter-LLM.** Déjà au cœur : le routeur EST cette portabilité.
- **D. Skills émergentes promues par l'humain.** (§6.)
- **E. Souveraineté / vie privée.** Substrat local ; règle « sensible → local seul ».
- **F. Anti-dérive factuelle.** Le LLM affirme « X à jour » alors que le journal dit
  l'inverse → alerter (flapper-de-faits).
- **G. ROI d'injection.** Le bloc injecté a-t-il changé la sortie ? Sinon, cesser.
- **H. « Le contexte ne ment pas » (C7 proposé).** Chaque bloc injecté porte son
  *why / when / fait-vs-croyance / frais-vs-périmé.*

---

## 8. Extension constitutionnelle proposée (à graver si validée)

C1-C6 inchangés. Deux ajouts :

- **C7 — « La mémoire ne ment pas à l'agent. »** Tout contexte restitué porte sa provenance
  et sa bi-temporalité : fait vs croyance, frais vs périmé, et *pourquoi* injecté. Aucun
  contexte « nu » sans traçabilité.
- **Le Plan de Contexte est *observe + restitue*, jamais *mute*.** Comme Shield et Predict :
  > ne crée aucun événement arbitraire (seulement des **captures** datées/sourcées) · ne
  > ferme aucune alerte · ne mute aucun fait · ne décide pas. Il **observe, restitue,
  > suggère** — et l'humain (ou le LLM *sous contrainte*) tranche.

Test structurel obligatoire, comme `test_predict.py`.

---

## 9. Ce que ce pivot n'est PAS

- Ce n'est **pas** un nouveau LLM, ni un fine-tuning, ni un agent autonome.
- Ce n'est **pas** « encore un mem0 » : mémoire seule = commodité ; gouvernance +
  observabilité d'usage + souveraineté, non.
- Ce n'est **pas** une réécriture d'AetherCore : c'est une **redirection** + une couche
  routeur par-dessus (voir `MULTISERVICE-AI-CONCEPTION.md`).
- Ce n'est **pas** un système qui agit à ta place. Jamais. Non négociable, par construction.
