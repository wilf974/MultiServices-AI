# Design — API REST web pour la mémoire centrale (roadmap-api-web)

> Date : 2026-06-22 · Statut : **approuvé** · Branche : `feature/webapi-rest`
> Demande source (journal, 22/06) : exposer une API HTTP/REST pour l'usage de la mémoire
> centrale depuis des **LLM web** (ChatGPT, Claude web, custom GPT, connecteurs), auth par
> clé/token, distincte de l'ingest mTLS CLI, **uniquement sur la version centralisée VPS,
> jamais sur l'install locale souveraine**.

## 1. Objectif & périmètre

Permettre à un **LLM web** (qui ne peut pas faire de mTLS ni de stdio MCP) de **lire** et
**écrire** la mémoire centrale via une API REST/JSON simple, documentée par OpenAPI (pour les
Custom GPT Actions et connecteurs).

**Décisions cadrées (validées) :**
- Périmètre : **lecture + écriture**.
- Auth : **token bearer par client**, mappé à une **source** dans un registre (token → source).
- Endpoints v1 : `GET /recall`, `POST /remember`, `GET /recent` (+ `/openapi.json`, `/docs`, `/health`).
- Exposition : **sous-domaine public `api-mem.example.com`**, token-only, rate-limité, **sans allowlist IP**.
- Framework : **FastAPI** (OpenAPI auto + validation Pydantic).
- **Central-only** : jamais sur l'install locale souveraine.

**Hors périmètre (YAGNI v1) :** OAuth, scopes lecture-seule par token, endpoints avancés
(`why`/`replay`/`forecast`), pagination au-delà de `k`, multi-tenant. Champs réservés prévus
pour extension (cf. §4).

## 2. Architecture & modules

Nouveau service central, deux modules (séparation logique pure / serveur) :

| Module | Rôle |
|---|---|
| `multiservice/webapi.py` | **Logique pure, testable** : chargement registre tokens, `resolve_token(token, registry) -> source \| None`, validation `kind`, modèles Pydantic (requêtes/réponses), construction de la réponse `recall`/`recent`. Aucun effet de bord. |
| `multiservice/webapi_server.py` | App **FastAPI** : routes, dépendance d'auth bearer, `main()` uvicorn. Câble `memory.py` (lecture) et la construction d'événement source-forcée de `ingest.py` (écriture) + `journal.append_events`. |

**Réutilisation (pas de duplication) :**
- Lecture : `memory.recall` / `memory.recall_semantic` (fusion hybride), `memory.recent` / `briefing`.
- Écriture : la construction d'`AetherEvent` avec **source imposée** (déjà dans `ingest.py`) + `journal.append_events`. `projlog.KINDS` pour valider `kind`.
- `config.py` pour `JOURNAL_PATH`, registre, embeddings.

## 3. Endpoints (v1)

Tous (sauf `/health`, `/openapi.json`, `/docs`) exigent `Authorization: Bearer <token>`.

### `GET /recall`
- Query : `q` (str, requis), `k` (int, défaut 10, max 50), `semantic` (bool, défaut true → fusion hybride ; false → lexical seul).
- 200 : `{ "results": [ {id, type, source, date, text, score, superseded} ] }`.
- Lecture seule. Pas d'écriture.

### `POST /remember`
- Body JSON : `{ "text": str (requis, 1..8192), "kind": str (défaut "note"), "session": str (défaut "web") }`.
- La **source est imposée par le token** (jamais lue du body ; un éventuel champ `source` est ignoré).
- `kind` validé contre `KINDS` → sinon **422**.
- 201 : `{ "id": "...", "source": "project:<client>" }`. Événement écrit avec `valid_to=null` (C3).

### `GET /recent`
- Query : `days` (int, défaut 7, max 90).
- 200 : `{ "since": ..., "days": N, "decisions": [...], "corrections": [...], "latest": [...] }` (forme de `memory.recent`).

### Utilitaires
- `GET /health` → 200 `{"status":"ok"}` (sans auth).
- `GET /openapi.json`, `GET /docs` → auto-FastAPI (sans auth ; nécessaire aux Custom GPT).
- `GET /` → 404.

## 4. Auth & registre des tokens

- En-tête `Authorization: Bearer <token>`.
- Registre **`/home/<user>/mem-secrets/webapi-tokens.json`** (hors `~/.aethercore`), monté **`:ro`** :
  ```json
  { "<token-opaque>": { "source": "project:chatgpt" } }
  ```
- `resolve_token` : token présent → `source` ; absent/inconnu → `None` → **401**.
- Champ réservé pour extension : `"scopes": ["read","write"]` (non appliqué en v1 ; tout token = lecture+écriture).
- Génération : `deploy/gen-webapi-token.sh <nom> [source]` → `openssl rand -hex 32` + entrée registre imprimée.
- **Révocation** = retirer l'entrée du registre (relu à chaque requête, comme l'ingest).

## 5. Sécurité

- **Token-only**, registre `:ro` hors `~/.aethercore` (le conteneur de lecture MCP ne le voit pas).
- **Public mais rate-limité** : nginx `limit_req` (zone dédiée, ex. 60 r/min) ; HTTPS obligatoire.
- **Écriture durcie** : source imposée par le token (**C2**, test critique : la source ne peut JAMAIS
  être fixée par le client) ; `kind` ∈ `KINDS` (sinon 422) ; plafond texte 8 Ko ; `valid_to=null` (**C3**).
- **Central-only** : le service n'est déployé/lancé que sur le VPS. Garde-fou : `main()` vérifie une
  variable d'activation explicite (`MULTISERVICE_WEBAPI_ENABLE=1`) et refuse de démarrer sinon.
- **Constitution** : l'écriture web reste une **observation** ; le filtre demeure à la promotion/service.
  Un token compromis = lecture/écriture du central → tokens = secrets révocables (retrait du registre).
- Journal RW limité au conteneur `mem-api` ; le registre est `:ro`.

## 6. Déploiement (artefacts)

- `deploy/Dockerfile.webapi` : `pip install ".[webapi]"`, `EXPOSE 8304`, `CMD multiservice-webapi`.
- `deploy/docker-run-webapi.sh` : conteneur `mem-api`, journal `:rw` (`/data`), registre `:ro` (`/secrets`),
  `-p 127.0.0.1:8304:8304`, `MULTISERVICE_WEBAPI_ENABLE=1`, `MULTISERVICE_WEBAPI_TOKENS=/secrets/webapi-tokens.json`.
- `deploy/gen-webapi-token.sh` : génère un token + entrée registre.
- `deploy/api-mem.example.com.nginx` : vhost public (TLS Let's Encrypt), `limit_req`, **sans** allowlist IP,
  `proxy_pass http://127.0.0.1:8304`. (Le `mem.example.com` IP-restreint reste inchangé.)
- `deploy/README.md` : section « API REST web ».
- `pyproject.toml` : extra `[webapi] = ["fastapi>=0.115", "uvicorn>=0.30"]` ; script `multiservice-webapi = "multiservice.webapi_server:main"`.
- Ports : 8302=mcp, 8303=ingest, **8304=webapi**.

## 7. Tests (TDD)

**Pur (`tests/test_webapi.py`)** : `resolve_token` (connu→source, inconnu/absent→None) ; validation `kind` ;
modèles Pydantic (bornes text/k/days).

**Endpoints (FastAPI `TestClient`, zéro réseau, `tests/test_webapi_server.py`)** :
- `GET /recall` : sans token → 401 ; mauvais token → 401 ; valide → 200 + `results`.
- `POST /remember` : **force la source du token** (un `source` fourni dans le body est ignoré — test
  critique sécurité) ; `kind` invalide → 422 ; valide → 201 `{id, source}` ; événement appendé `valid_to=null`.
- `GET /recent` → 200.
- `GET /health` → 200 sans auth.
- Garde-fou central-only : `main()` sans `MULTISERVICE_WEBAPI_ENABLE` → refuse de démarrer.

Le journal de test pointe vers un fichier temporaire (pas le journal réel). Embeddings : `FakeEmbedder`
si la branche sémantique est testée.

## 8. Découpage en tâches (pour le plan)

1. `webapi.py` (pur) + `tests/test_webapi.py`.
2. `webapi_server.py` (FastAPI) + `tests/test_webapi_server.py` (TestClient).
3. `pyproject` (extra `[webapi]` + script) + garde-fou central-only.
4. Artefacts déploiement (`Dockerfile.webapi`, `docker-run-webapi.sh`, `gen-webapi-token.sh`, vhost, README).
5. Déploiement VPS (root) — manuel, hors auto-exécution.
