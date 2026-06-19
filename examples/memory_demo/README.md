# Démo — DunkBot 3000 🥞🤖

Une démo **concrète** et **100 % fictive** (aucune donnée réelle) qui montre ce que MultiService IA
apporte : **la même question, sans mémoire puis avec.**

![Démo Memory Arcade](arcade_demo.gif)

L'histoire : on monte un robot qui retourne des pancakes. Jour 1, on décide un moteur **NEMA-17**.
Jour 3, le terrain corrige : *« il cale, passe à un servo MG996R »*. La question posée est
« quel moteur pour le bras ? ».

- **Sans mémoire** : l'agent répond à l'aveugle — au pire il re-recommande le NEMA-17 abandonné.
- **Avec MultiService IA** : `brief()` remonte la décision **marquée périmée (C3)**, sert la
  **vérité courante** (le servo), retrouve le **code** (`has_code`) et la **nomenclature**
  (`has_table`), le tout sourcé et daté.

## Lancer

```bash
# comparaison en console (aucun modèle requis : démontre la couche mémoire)
python examples/memory_demo/compare.py

# (optionnel) exporter les événements fictifs en JSON, pour inspection / autres outils
# — le GUI arcade.html, lui, embarque déjà sa propre copie (autonome, sans serveur)
python examples/memory_demo/seed_demo.py
```

## GUI

Ouvre **`arcade.html`** dans un navigateur (double-clic — aucun serveur, aucune donnée réelle).
Tape une question ou clique un préréglage : le panneau « avec mémoire » affiche les souvenirs avec
leur provenance, **raye le fait périmé (C3)** et met en avant la vérité courante. La timeline montre
le journal append-only — le périmé est *rayé, jamais supprimé*.

> Tout est inventé pour la démo. Le vrai moteur fait la même chose, en lecture seule, sur ton
> journal local — qui, lui, ne quitte jamais ta machine.
