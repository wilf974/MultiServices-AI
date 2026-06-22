# Design — Ingest distant authentifié (écriture vers le journal central, phase 2)

> Date : 2026-06-22 · Projet : MultiService IA · Statut : approuvé (design), en revue (spec)
> Session : `serveur-memoire-central`. Suite de la phase 1 (serveur de lecture HTTPS).
> Pattern hérité d'AetherCore : « seul chemin d'écriture distant = `/api/ingest*` (mTLS+HMAC) ».

## 1. Problème & objectif

La phase 1 expose la mémoire centrale en **lecture seule**. Aucun poste distant ne peut **écrire**
(ex. le poste bureau ne peut pas journaliser une décision dans la mémoire partagée). On veut une
**surface d'écriture distante authentifiée** : un poste autorisé POST un événement, le serveur le
valide et l'**append** au journal central.

**Contrainte constitutionnelle (D5)** : le MCP reste **lecture seule**. L'écriture passe par un
**endpoint séparé** (pas un outil MCP), exactement comme AetherCore `/api/ingest`.

## 2. Objectifs / Non-objectifs

**Objectifs**
- Endpoint `POST /ingest` sur `mem.woutils.com`, **mTLS obligatoire**, qui valide et append un
  `AetherEvent` au journal central.
- **Sécurité maximale** : mTLS (CA dédiée) + HMAC du corps + anti-rejeu (timestamp + nonce) +
  allowlist IP + **provenance imposée** par l'identité du certificat.
- Conteneur d'ingest **séparé** (journal monté **RW**) ; le conteneur de lecture reste **`:ro`**.
- Client CLI `memlog`-over-HTTP sur chaque poste.
- Les événements produits à distance sont **identiques** à ceux de `projlog` local (même C2/C3).

**Non-objectifs (YAGNI)**
- Capture de tours complets (on se limite aux kinds `projlog` : decision/correction/note/
  hypothesis/observation/validation).
- UI, rotation automatique des certs, fédération multi-CA, suppression/édition distante.

## 3. Architecture

```
poste (cert client mTLS + cle HMAC + memlog-http)
  --TLS + mTLS--> nginx :8443 (mem.woutils.com)  [allowlist IP]
     location /mcp    -> bearer (lecture)          -> conteneur READ   (journal :ro)  [inchange]
     location /ingest -> ssl_verify_client SUCCESS -> conteneur INGEST (journal RW, 127.0.0.1:8303)
                          | verifie HMAC(body) avec la cle du CN
                          | verifie ts (fenetre +-300s) + nonce (non vu)
                          | source = mapping[CN] (imposee, C2)  ; valide le kind
                          | build AetherEvent (id uuid4, valid_from=now) ; APPEND journal
```

Même vhost qu'en phase 1 : on ajoute au server `ssl_client_certificate <CA mem>` +
`ssl_verify_client optional`. `/mcp` ignore le cert (bearer) ; `/ingest` exige le cert.

## 4. Contrat d'API

`POST /ingest` — corps JSON :
```json
{ "text": "<non vide>",
  "kind": "decision|correction|note|hypothesis|observation|validation",
  "session": "<sujet>",
  "ts": "<ISO8601 UTC>",
  "nonce": "<chaine aleatoire unique>",
  "data": { } }
```
En-têtes : certificat client (mTLS) + `X-Mem-Signature: <hex HMAC-SHA256 du corps brut>`.
nginx ajoute `X-Client-CN: <CN du cert>` (depuis `$ssl_client_s_dn_cn`).

Réponses :
| Code | Cas |
|---|---|
| `201` | créé — corps `{ "id": "<uuid>", "source": "project:<...>" }` |
| `403` | pas de certificat client valide (nginx) |
| `401` | CN inconnu, HMAC invalide, ou `ts` hors fenêtre (±300 s) |
| `409` | `nonce` déjà vu (rejeu) |
| `422` | payload invalide (kind inconnu, `text` vide, JSON malformé) |

## 5. Authentification, provenance & anti-rejeu

- **mTLS** : CA dédiée `/etc/nginx/mtls/mem/ca.crt`. nginx `ssl_verify_client optional` au server,
  `if ($ssl_client_verify != SUCCESS) { return 403; }` dans `/ingest`. CN passé via `X-Client-CN`.
- **Registre serveur** `ingest-clients.json` : `{ "<CN>": { "source": "project:<nom>",
  "hmac_key": "<hex>" } }`. Monté **read-only** dans le conteneur ingest, jamais exposé.
- **HMAC** : le service recalcule `HMAC-SHA256(corps_brut, hmac_key[CN])` et compare en temps
  constant à `X-Mem-Signature`. Corrobore l'identité au-delà de l'en-tête nginx (protège le saut
  nginx→conteneur en clair sur localhost). Échec → `401`.
- **Provenance (C2) imposée** : `source = registre[CN].source`. Toute `source` du payload est
  **ignorée**. → un poste ne peut pas usurper la source d'un autre.
- **Anti-rejeu** : `ts` doit être dans **±300 s** de l'heure serveur (sinon `401`) ; `nonce` ne doit
  pas figurer dans le **nonce-store** persistant (sinon `409`). Le store garde `(nonce, ts)` et
  **purge** les entrées plus vieilles que la fenêtre.

## 6. Composants & fichiers

### Code (testé)
- `multiservice/ingest.py` — logique **pure** (IO au bord) :
  - `verify_hmac(body: bytes, signature: str, key: str) -> bool` (comparaison constante)
  - `check_freshness(ts: str, now: datetime, window_s: int = 300) -> bool`
  - `NonceStore(path)` : `seen(nonce) -> bool`, `add(nonce, ts)`, `prune(now, window_s)`
  - `build_ingest_event(text, kind, source, session, data, now) -> AetherEvent`
    (réutilise la construction d'événement de `projlog` — voir refactor ci-dessous)
  - `ingest(payload: dict, cn: str, signature: str, body: bytes, registry: dict,
    journal_path, nonce_store, now) -> dict` : orchestration, renvoie `{status, id?/error}`.
- `multiservice/ingest_server.py` — app **Starlette** : route `POST /ingest`, lit `X-Client-CN` +
  `X-Mem-Signature` + corps brut, appelle `ingest()`, mappe le statut → code HTTP. `main()` = uvicorn
  (`MULTISERVICE_INGEST_HOST`/`PORT`, défaut `0.0.0.0:8303`).
- `multiservice/memlog_http.py` — **client CLI** : `memlog-http "<texte>" --kind <k> --session <s>`.
  Lit la config (env) : URL, chemin cert+clé client, clé HMAC. Construit le payload (ts=now,
  nonce=aléatoire), signe, POST avec le cert. Affiche l'`id` renvoyé.
- **Refactor DRY** : extraire la construction d'événement de `multiservice/projlog.py` dans une
  fonction partagée (`projlog.build_event(...)` ou `events`), utilisée par `projlog` **et**
  `ingest`, pour que capture locale et distante produisent des événements identiques.

### Infra (déploiement)
- `deploy/Dockerfile.ingest`, `deploy/docker-run-ingest.sh` (journal **RW** + registre `:ro` +
  nonce-store **RW** + `MULTISERVICE_JOURNAL`/`HOST`/`PORT`).
- `deploy/gen-mtls.sh` — crée la CA dédiée + un cert client (CN paramétrable) + une clé HMAC, et
  imprime l'entrée à ajouter au registre.
- Ajout `location /ingest` au vhost `deploy/mem.woutils.com.nginx` + directives mTLS au server.

### Tests
- `tests/test_ingest.py` — **régression** : HMAC ok/ko (constant-time), `ts` hors fenêtre → refus,
  `nonce` rejoué → refus, **source forcée** par CN (payload.source ignorée), kind invalide → refus,
  `text` vide → refus, append append-only (1 ligne, id uuid), purge du nonce-store.

## 7. Écriture & concurrence

Le conteneur ingest monte le journal **RW** ; le conteneur lecture reste **`:ro`**. `ingest` append
un événement **neuf** (id uuid4) en `O_APPEND` ; `sync.merge_journal` **append** aussi (jamais de
réécriture). Pas de collision d'`id`, pas de clobber. Le serveur de lecture (read_events par requête)
reflète immédiatement les nouveaux événements.

## 8. Gestion d'erreurs

Codes ci-dessus (§4). Le conteneur `--restart unless-stopped`. Corps malformé / HMAC manquant →
`422`/`401`. Le nonce-store et le registre absents → l'ingest refuse (fail-closed) en `401`/`500`
avec log clair, plutôt que d'accepter sans contrôle.

## 9. Sécurité / souveraineté

mTLS (CA dédiée) + HMAC + nonce + fenêtre temporelle + allowlist IP + provenance forcée +
append-only + journal RW **isolé** du conteneur lecture. Le MCP reste **lecture seule** (D5). Tout
sur le VPS ; aucune API hébergée. Le registre (clés HMAC) et les clés privées des certs ne sont
**jamais** journalisés.

## 10. Déploiement (étapes root)

1. `deploy/gen-mtls.sh` → CA `/etc/nginx/mtls/mem/`, cert client par poste, clé HMAC, entrée registre.
2. Conteneur ingest : `docker build -f deploy/Dockerfile.ingest` + `docker-run-ingest.sh`.
3. nginx : ajouter les directives mTLS + `location /ingest` au vhost, `nginx -t && reload`.
4. Distribuer à chaque poste : cert client + clé + clé HMAC + config `memlog-http`.

## 11. Tests de bout en bout (smoke)

cert valide + HMAC bon → `201` ; sans cert → `403` ; HMAC faux → `401` ; nonce rejoué → `409` ;
puis `recall`/`recent` via le serveur de lecture **confirme** l'événement écrit.

## 12. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Vol d'un cert+clé client | révocation par cert (CA dédiée) + allowlist IP + clé HMAC distincte |
| Rejeu d'une requête capturée | fenêtre ±300 s + nonce-store |
| Usurpation de source | source imposée par CN (registre), payload.source ignorée |
| nginx→conteneur en clair (localhost) | HMAC vérifié dans le conteneur (pas de confiance aveugle au header CN) |
| Deux écrivains du journal | append-only des deux côtés (ingest + merge), id uuid uniques |
