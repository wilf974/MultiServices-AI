# Protocole de journalisation mémoire — à donner à un LLM/agent

> Statut : **actif**. Remplace `docs/CAPTURE-CONVENTION.md` (basé sur `projlog`, périmé sur ce poste).
> Distille la doctrine Fable (`orchestrateur-journalisation/`) + les règles obligatoires du poste :
> écriture centrale directe via `memlog-http` (mTLS+HMAC, source imposée par le CN du cert), lecture
> **read-only** via le MCP. À coller dans les instructions d'un LLM (`CLAUDE.md`/`AGENTS.md`/system prompt).

## 1. QUAND — le test en 3 questions (avant CHAQUE écriture)

1. **Le voudrai-je encore dans 2 semaines ?** Non → bruit.
2. **Ça contredit / précise un fait existant ?** Oui → signal (souvent une *correction*).
3. **C'est déjà dans git / un ticket / un doc versionné ?** Oui et rien d'autre → **ne pas écrire** (au plus une note qui *pointe*).

→ Q1 **ou** Q2 = oui → écrire. Q3 seul = ne pas écrire.
**Règle mère : journaliser ce qui change une décision future — rien d'autre.**

**NE JAMAIS journaliser :** bavardage · micro-étapes (« j'ouvre le fichier », « les tests passent ») ·
confirmations sans enjeu · contenu déjà versionné (le code vit dans git ; la mémoire *pointe*, ne
duplique pas) · **aucun secret / token / identifiant / IP / URL interne** (append-only = ineffaçable).

## 2. QUOI — 6 types, chacun son déclencheur

| kind | Déclencheur | Contenu minimal |
|---|---|---|
| `decision` | un choix arrêté qui engage la suite | le choix **+ le pourquoi + les alternatives écartées** |
| `correction` | un fait mémorisé devenu faux/imprécis/périmé | la version corrigée **+ ce qu'elle corrige** (`--closes`) |
| `validation` | un résultat vérifié (test, revue) | ce qui est validé + la méthode |
| `observation` | un fait constaté (mesure, incident) utile plus tard | le fait + son contexte |
| `hypothesis` | une piste plausible non vérifiée, coûteuse à re-trouver | l'hypothèse + comment la vérifier (confidence < 0.8) |
| `note` | info durable sans autre catégorie | l'info (+ emplacement si c'est un livrable) |

## 3. COMMENT — sur ce poste, `memlog-http` (chemin obligatoire)

```bash
memlog-http "<le fait, autoporté>" --kind <type> --session <sujet-kebab-case>
```

- **La source est imposée par le certificat** (`project:maison` sur ce poste) → **ne pas la fixer**.
- **`--session`** = le sujet stable de la session, en **kebab-case** (ex. `chiffrement-crypto-shred`).
- **Correction = clôture C3 ciblée** (le serveur refuse `--closes` sans `--kind correction`) :

```bash
memlog-http "<version corrigée>" --kind correction --closes "<id1,id2>" --session <sujet>
```

- Env requis une fois par shell (certs `C:\mem`) : `MEM_INGEST_URL`, `MEM_CLIENT_CERT`, `MEM_CLIENT_KEY`,
  `MEM_HMAC_KEY`. Recette : `deploy/SETUP-POSTE-CLIENT.md`.
- **Variantes de canal** : LLM web → API REST `POST /remember` (token) ; modèle Ollama en boucle chat →
  `/note`, `/correct`, ou l'outil gardé `remember` (source forcée `project:ollama`, non-autoritatif).

## 4. RÈGLES D'OR

- **Recall AVANT d'écrire** (dédup) : interroger la mémoire (MCP `recall`/`brief`) ; si le fait existe et a
  changé → **correction ciblée**, pas un nouvel event. *(L'ingest refuse aussi les doublons exacts vivants — filet, pas excuse.)*
- **Texte autoporté** : compréhensible sans relire la conversation (≥ 15 car., le qui/quoi/pourquoi dedans).
- **1 fait = 1 event** : deux décisions distinctes = deux écritures.
- **Lecture = lecture seule** via le MCP (`recall`, `brief`, `recent`, `lessons`, `why`…) ; **seul `memlog-http` écrit**.
- **Annoncer chaque écriture** (id + source renvoyés).

## 5. FIN DE SESSION — le trou n°1 en pratique

Se demander : **« ai-je pris une décision / obtenu une validation / heurté une correction non
journalisée ? »** Si oui → l'écrire avant de clore.

---

## Version courte (à injecter dans un `CLAUDE.md` / `AGENTS.md`)

```md
## Mémoire — capture
Journaliser SEULEMENT ce qui change une décision future (test : le voudrai-je dans 2 semaines ? ça
contredit un fait existant ?). Jamais : bavardage, micro-étapes, contenu déjà dans git, secrets/tokens.
Écrire via : `memlog-http "<fait autoporté>" --kind <decision|correction|validation|observation|hypothesis|note> --session <sujet-kebab-case>`
(source imposée par le cert, ne pas la fixer). Correction ciblée : `--kind correction --closes "<ids>"`.
Recall AVANT d'écrire (dédup). Lecture = read-only via le MCP. Annoncer chaque écriture (id+source).
Fin de session : « une décision/validation/correction non journalisée ? » → l'écrire.
```
