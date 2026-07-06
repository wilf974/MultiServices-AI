# MultiService IA — moteur de mémoire *versionnée* pour assistants IA

> *Event sourcing appliqué à la cognition des LLM. Git pour la connaissance.*
>
> *« Les LLM oublient. Ta mémoire ne devrait pas. »*

## Ce que c'est (concret)

Un **serveur de mémoire persistante, local et souverain**, que n'importe quel assistant IA
interroge **par API ou MCP**. Ce n'est **pas** un vector store : c'est un **journal de vérité
versionné**.

## Le principe

Le **journal append-only est la source de vérité**. Tout le reste n'en est qu'une projection :

- les **embeddings** ne sont qu'un **index** ;
- le **cache** n'est qu'une **optimisation** ;
- les **briefings** ne sont qu'une **vue**.

À partir du journal, tout est **lecture** — on ne mute jamais l'histoire.

## Le cœur (ce qui n'existe presque nulle part)

Une correction ne *remplace* pas un fait : elle le **clôture** (bi-temporalité). On peut donc
demander :

- *« Que croyait-on le 14 février ? »*
- *« Pourquoi a-t-on abandonné cette hypothèse ? »*

Très peu de mémoires savent répondre. C'est **Git appliqué à la connaissance** — et c'est le
différenciateur.

## Ce qui en découle

- **Provenance obligatoire** — chaque fait est sourcé et daté. Fin des affirmations sans trace.
- **Reconstruction d'état** — une session neuve reconstruit l'histoire intellectuelle d'un projet
  depuis la seule mémoire : théorie courante, décisions, corrections, hypothèses réfutées.
- **Mémoire agentique** — le modèle local interroge et écrit sa mémoire, sous garde-fous.
- **Souveraineté** — inférence et embeddings 100 % locaux (Ollama) ; un mode serveur central existe
  mais reste une **option** pour partager un journal entre machines. Ton journal ne part jamais.

## Auto-curation

Une mémoire finit toujours par dériver : doublons, reformulations, informations obsolètes.
MultiService IA **détecte** ces dérives, **propose** fusions et clôtures, **refuse** les nouveaux
doublons à l'écriture, et produit un **rapport quotidien**. **L'humain valide toujours la décision.
Le journal d'origine reste intact.**

## Positionnement

Ce projet ne concurrence pas les « mémoires » LLM (OpenAI, Mem0, Zep, Graphiti…). C'est un **moteur
d'event sourcing spécialisé pour la cognition des LLM** : retrouver non seulement *ce qu'on sait*,
mais **pourquoi**, **depuis quand c'était vrai**, et **comment cette connaissance a évolué**.

Un angle défendable auprès d'un public technique qui comprend la valeur de la **traçabilité**, de
l'**auditabilité** et de la **reconstruction d'état**.

## Cas d'usage

- **Développement logiciel** — décisions d'architecture, bugs résolus et leurs *raisons*.
- **Recherche** — évolution des hypothèses et corrections sur des mois/années.
- **Juridique / médical** — traçabilité absolue des raisonnements.
- **Agents autonomes** — des IA qui apprennent de leurs erreurs sans oublier leur historique.

## Maturité

Moteur fonctionnel, suite de tests exhaustive et verte, chaque fonctionnalité livrée avec son test
de régression. Le projet suit **son propre développement** dans sa mémoire (dogfooding). Licence
**Apache-2.0**.

---

*Une mémoire classique répond « qu'est-ce que je sais ? ». MultiService IA répond aussi « qu'est-ce
qui est encore vrai ? », « qu'est-ce qui a changé ? » et « pourquoi ? » — localement, et sous ton
contrôle.*
