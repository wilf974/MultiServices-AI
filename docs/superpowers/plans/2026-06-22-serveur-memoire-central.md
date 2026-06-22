# Serveur de mémoire central (MVP lecture seule, HTTPS) — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Exposer les 12 outils MCP **lecture seule** de MultiService IA en HTTPS, via un conteneur Docker (journal monté `:ro`) derrière nginx, accessible depuis des postes distants par bearer token + allowlist IP.

**Architecture:** On réutilise le `build_server()` FastMCP existant et on ajoute un lancement **streamable-http**. Le conteneur sert le journal en lecture seule (montage `:ro` = garantie OS de la constitution D5). nginx termine TLS, filtre par IP, vérifie le token, rate-limit et logue. Aucun nouvel outil, aucune écriture distante (reportée phase 2).

**Tech Stack:** Python 3.13, FastMCP (paquet `mcp`), pytest, Docker, nginx, certbot.

## Global Constraints

- **Python >= 3.11** (cible VM = 3.13.5). Valeur du `pyproject.toml` inchangée.
- **MCP lecture seule (D5)** : aucune écriture du journal via la surface MCP. Vérification structurelle obligatoire.
- **Embeddings/inférence 100% locaux** : aucune API hébergée introduite.
- **Sorties console en ASCII** (pas d'accents dans les `print`/scripts shell ; les `.md` peuvent garder les accents).
- **Port interne** : `8302` (aethercore occupe 8301).
- **Allowlist IP** : `<IP_PUBLIQUE_MAISON>` (maison/public) et `<IP_PUBLIQUE_BUREAU>` (bureau).
- **Tokens séparés dès maintenant** : `MEM_READ_TOKEN` (utilisé) ; `MEM_WRITE_TOKEN` réservé, non utilisé (phase 2).
- **Chaque sprint laisse un test de régression permanent** (règle projet).
- **Ne jamais `git commit` depuis le bac à sable** : committer depuis la machine Windows réelle.

---

### Task 1 : Lancement HTTP (streamable-http) + tests de régression

**Files:**
- Modify: `multiservice/mcp_server.py` (ajout en fin de fichier, après `main()`)
- Modify: `pyproject.toml` (section `[project.scripts]`)
- Test: `tests/test_mcp_http.py` (créer)

**Interfaces:**
- Consumes: `multiservice.mcp_server.build_server(journal_path: str | None) -> FastMCP` (existant, inchangé).
- Produces:
  - `build_http_server(host: str | None = None, port: int | None = None, journal_path: str | None = None) -> FastMCP`
  - `main_http() -> None`
  - console script `multiservice-mcp-http` → `multiservice.mcp_server:main_http`

- [ ] **Step 1 : Écrire les tests qui échouent**

Créer `tests/test_mcp_http.py` :

```python
"""Regression : la surface HTTP reutilise build_server (parite d'outils) et reste LECTURE SEULE."""
from __future__ import annotations

import asyncio

import pytest

pytest.importorskip("mcp")  # SDK requis pour FastMCP

from multiservice.mcp_server import build_server, build_http_server

READ_TOOLS = {
    "recall", "why", "recall_semantic", "replay", "replay_event", "forecast",
    "brief", "recent", "usage", "reasoning", "lessons", "index_status",
}


def test_http_server_exposes_exactly_the_readonly_tools(tmp_path):
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    srv = build_server(str(jp))
    names = {t.name for t in asyncio.run(srv.list_tools())}
    assert names == READ_TOOLS  # parite + aucun outil d'ecriture ajoute par megarde


def test_read_tool_never_writes_the_journal(tmp_path):
    jp = tmp_path / "sub" / "j.jsonl"   # n'existe pas
    srv = build_server(str(jp))
    asyncio.run(srv.call_tool("recent", {"days": 7}))
    assert not jp.exists()              # la lecture ne cree ni n'ecrit jamais le journal


def test_build_http_server_reads_port_from_env(monkeypatch, tmp_path):
    jp = tmp_path / "j.jsonl"
    jp.write_text("", encoding="utf-8")
    monkeypatch.setenv("MULTISERVICE_HTTP_PORT", "8302")
    srv = build_http_server(journal_path=str(jp))
    assert srv.settings.port == 8302
    assert srv.settings.host == "0.0.0.0"
```

- [ ] **Step 2 : Lancer les tests pour vérifier qu'ils échouent**

Run: `pytest tests/test_mcp_http.py -v`
Expected: FAIL avec `ImportError: cannot import name 'build_http_server'`

- [ ] **Step 3 : Implémenter le lancement HTTP**

Ajouter à la fin de `multiservice/mcp_server.py` (après `main()`, avant le `if __name__`) :

```python
def build_http_server(host: str = None, port: int = None, journal_path: str = None):
    """Serveur FastMCP configure pour le transport streamable-http (conteneur).
    host/port surchargeables par env (MULTISERVICE_HTTP_HOST / MULTISERVICE_HTTP_PORT)."""
    import os
    h = host or os.environ.get("MULTISERVICE_HTTP_HOST", "0.0.0.0")
    p = int(port if port is not None else os.environ.get("MULTISERVICE_HTTP_PORT", "8302"))
    srv = build_server(journal_path)
    srv.settings.host = h
    srv.settings.port = p
    return srv


def main_http() -> None:
    """Point d'entree HTTP : sert la memoire en LECTURE SEULE via streamable-http."""
    build_http_server().run(transport="streamable-http")
```

- [ ] **Step 4 : Ajouter le point d'entrée console**

Dans `pyproject.toml`, section `[project.scripts]`, ajouter la ligne :

```toml
multiservice-mcp-http = "multiservice.mcp_server:main_http"   # surface HTTP lecture seule (conteneur)
```

Puis réinstaller en editable pour enregistrer le script : `pip install -e ".[mcp]"`

- [ ] **Step 5 : Lancer les tests pour vérifier qu'ils passent**

Run: `pytest tests/test_mcp_http.py -v`
Expected: 3 PASS

- [ ] **Step 6 : Lancer toute la suite (non-régression)**

Run: `pytest -q`
Expected: tous verts (>= 92 + 3 nouveaux)

- [ ] **Step 7 : Commit**

```bash
git add multiservice/mcp_server.py pyproject.toml tests/test_mcp_http.py
git commit -m "feat(mcp): lancement streamable-http (lecture seule) + tests de regression"
```

---

### Task 2 : Artefacts de déploiement (Docker + nginx)

**Files:**
- Create: `deploy/Dockerfile.mem`
- Create: `deploy/docker-run-mem.sh`
- Create: `deploy/mem.example.com.nginx`
- Create: `deploy/README.md`

**Interfaces:**
- Consumes: console script `multiservice-mcp-http` (Task 1).
- Produces: image Docker `mem-mcp` ; conteneur publiant `127.0.0.1:8302` ; modèle de site nginx.

- [ ] **Step 1 : Créer le Dockerfile**

`deploy/Dockerfile.mem` :

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY multiservice ./multiservice
RUN pip install --no-cache-dir ".[mcp]"
EXPOSE 8302
ENV MULTISERVICE_HTTP_HOST=0.0.0.0 \
    MULTISERVICE_HTTP_PORT=8302
CMD ["multiservice-mcp-http"]
```

- [ ] **Step 2 : Créer le script de lancement du conteneur**

`deploy/docker-run-mem.sh` (le journal est monté en LECTURE SEULE `:ro`) :

```bash
#!/usr/bin/env bash
# Lance le conteneur de memoire centrale. Journal monte en LECTURE SEULE (:ro) = garantie OS (D5).
set -euo pipefail
docker rm -f mem-mcp 2>/dev/null || true
docker run -d --name mem-mcp --restart unless-stopped \
  -p 127.0.0.1:8302:8302 \
  -v /home/<user>/.aethercore:/data:ro \
  -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl \
  -e MULTISERVICE_EMBED=/data/embeddings-llm.jsonl \
  -e MULTISERVICE_CACHE=/data/cache-llm.jsonl \
  -e MULTISERVICE_SEMCACHE=/data/semcache-llm.jsonl \
  -e MULTISERVICE_SKILLS=/data/skills \
  -e MULTISERVICE_HTTP_HOST=0.0.0.0 -e MULTISERVICE_HTTP_PORT=8302 \
  mem-mcp
echo "mem-mcp lance sur 127.0.0.1:8302 (journal en lecture seule)"
```

- [ ] **Step 3 : Créer le modèle de site nginx**

`deploy/mem.example.com.nginx` (remplacer `__MEM_READ_TOKEN__` et les chemins de certificat au déploiement) :

```nginx
map $http_authorization $mem_ok { default 0; "Bearer __MEM_READ_TOKEN__" 1; }
limit_req_zone $binary_remote_addr zone=mem:10m rate=30r/m;

server {
    listen 80;
    server_name mem.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name mem.example.com;

    # ssl_certificate / ssl_certificate_key : ajoutes par certbot

    allow <IP_PUBLIQUE_MAISON>;     # maison / IP publique
    allow <IP_PUBLIQUE_BUREAU>;   # bureau
    deny all;

    access_log /var/log/nginx/mem.access.log;
    error_log  /var/log/nginx/mem.error.log;

    location /mcp {
        if ($mem_ok = 0) { return 401; }
        limit_req zone=mem burst=10 nodelay;
        proxy_pass http://127.0.0.1:8302;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_buffering off;            # streamable-http / SSE
        proxy_read_timeout 1h;
    }
}
```

- [ ] **Step 4 : Créer le guide de déploiement**

`deploy/README.md` :

````markdown
# Déploiement — serveur de mémoire central (mem.example.com)

> MVP lecture seule. Étapes 2 à 5 = **root** sur la VM. Voir le spec
> `docs/superpowers/specs/2026-06-22-serveur-memoire-central-design.md`.

## 1. DNS (utilisateur)
`mem.example.com` → A `<IP_PUBLIQUE_MAISON>`, TTL 300.

## 2. Mettre le code à jour sur la VM (depuis Windows, en LOCAL)
```bash
cd "/c/Users/<user>/Claude/Projects/MultiService IA"
git archive --format=tar feature/serveur-memoire-central | \
  ssh -p <SSH_PORT> <user>@<VPS_LAN> 'tar -x -C /home/<user>/multiservice'
```

## 3. Construire l'image et lancer le conteneur (VM)
```bash
cd /home/<user>/multiservice
docker build -f deploy/Dockerfile.mem -t mem-mcp .
bash deploy/docker-run-mem.sh
docker ps --filter name=mem-mcp
```

## 4. Générer le token de lecture et le site nginx (root)
```bash
MEM_READ_TOKEN=$(openssl rand -hex 32); echo "$MEM_READ_TOKEN"   # NOTER ce token
sed "s/__MEM_READ_TOKEN__/$MEM_READ_TOKEN/" \
  /home/<user>/multiservice/deploy/mem.example.com.nginx \
  > /etc/nginx/sites-enabled/mem.example.com
certbot --nginx -d mem.example.com
nginx -t && systemctl reload nginx
```

## 5. Brancher un poste client (n'importe quelle machine, IP allowlistée)
```bash
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp \
  --header "Authorization: Bearer <MEM_READ_TOKEN>"
claude mcp list    # -> multiservice-memory ... connected
```

## Smoke tests (depuis une IP allowlistée)
```bash
# avec token -> 200/handshake
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <MEM_READ_TOKEN>" https://mem.example.com/mcp
# sans token -> 401
curl -s -o /dev/null -w "%{http_code}\n" https://mem.example.com/mcp
# depuis une IP NON listee -> 403
```

## Rotation du token
Éditer la valeur dans `/etc/nginx/sites-enabled/mem.example.com`, puis
`nginx -t && systemctl reload nginx`, et mettre à jour le header des clients.

## Limite connue (MVP)
`recall_semantic` nécessite Ollama + index, **absents du conteneur MVP** → cet outil
renverra une erreur. Les 11 autres outils (lexicaux) fonctionnent. Sémantique = phase 2.
`MEM_WRITE_TOKEN` : réservé, non utilisé (l'écriture distante est phase 2).
````

- [ ] **Step 5 : Vérifier que l'image se construit en local (Docker Desktop)**

Run: `docker build -f deploy/Dockerfile.mem -t mem-mcp .` (depuis la racine du repo)
Expected: build OK, `Successfully tagged mem-mcp:latest`

- [ ] **Step 6 : Vérifier que le conteneur démarre et écoute en local**

```bash
docker rm -f mem-test 2>/dev/null || true
docker run -d --name mem-test -p 127.0.0.1:8302:8302 mem-mcp
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8302/mcp   # une reponse HTTP (pas 000/refused)
docker rm -f mem-test
```
Expected: un code HTTP (ex. 400/406/200 selon le handshake), **pas** `000` ni connexion refusée → le serveur tourne.

- [ ] **Step 7 : Commit**

```bash
git add deploy/
git commit -m "feat(deploy): image Docker (journal :ro) + site nginx + guide mem.example.com"
```

---

### Task 3 : Déploiement & vérification sur la VM (étapes root)

**Files:** aucun fichier de code — exécution des étapes de `deploy/README.md`.

**Interfaces:**
- Consumes: image `mem-mcp` (Task 2), site nginx (Task 2), branche `feature/serveur-memoire-central`.
- Produces: endpoint `https://mem.example.com/mcp` opérationnel ; clients connectés.

- [ ] **Step 1 : DNS** — créer `mem.example.com` A → `<IP_PUBLIQUE_MAISON>` (TTL 300). *(utilisateur)*

- [ ] **Step 2 : Pousser le code sur la VM** (depuis Windows, en LOCAL)

```bash
cd "/c/Users/<user>/Claude/Projects/MultiService IA"
git archive --format=tar feature/serveur-memoire-central | \
  ssh -p <SSH_PORT> <user>@<VPS_LAN> 'tar -x -C /home/<user>/multiservice'
```
Expected: pas d'erreur.

- [ ] **Step 3 : Construire + lancer le conteneur** (VM, <user> — docker accessible sans root)

```bash
ssh -p <SSH_PORT> <user>@<VPS_LAN> 'cd ~/multiservice && docker build -f deploy/Dockerfile.mem -t mem-mcp . && bash deploy/docker-run-mem.sh && docker ps --filter name=mem-mcp'
```
Expected: conteneur `mem-mcp` `Up`, publié sur `127.0.0.1:8302`.

- [ ] **Step 4 : Site nginx + token + TLS** (root, l'utilisateur exécute — voir `deploy/README.md` §4)

Générer `MEM_READ_TOKEN` (`openssl rand -hex 32`), instancier le site, `certbot --nginx -d mem.example.com`, `nginx -t && systemctl reload nginx`.
Expected: `nginx -t` = `syntax is ok` / `test is successful`.

- [ ] **Step 5 : Smoke tests** (depuis une IP allowlistée)

```bash
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <TOKEN>" https://mem.example.com/mcp   # 200/handshake
curl -s -o /dev/null -w "%{http_code}\n" https://mem.example.com/mcp                                       # 401
```
Expected: token OK → 2xx/handshake ; sans token → 401 ; IP non listée → 403.

- [ ] **Step 6 : Brancher un poste client + vérifier**

```bash
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp --header "Authorization: Bearer <TOKEN>"
claude mcp list
```
Expected: `multiservice-memory ... connected`. Tester `recent` dans une session → renvoie les events.

- [ ] **Step 7 : Consigner (règle projet)**

```bash
cd "/c/Users/<user>/Claude/Projects/MultiService IA"
python -m multiservice.projlog "Serveur memoire central MVP (lecture seule) EN SERVICE : https://mem.example.com/mcp, conteneur Docker journal :ro, nginx allowlist IP + bearer MEM_READ_TOKEN + rate-limit + logs. Poste(s) distant(s) branche(s) via claude mcp add --transport http. Ecriture distante = phase 2." --kind decision --source project:MultiService-IA --session serveur-memoire-central
```
Puis mettre à jour la note Obsidian `Déploiement MCP sur la VM (root)` (section serveur central) + committer le spec/plan. Annoncer l'écriture.

---

## Self-Review (effectué)

- **Couverture du spec :** §3 archi → T1+T2 ; §4 composants → T1 (code) + T2 (infra) ; §5 contrat client → T2 README + T3 S6 ; §6 nginx → T2 S3 ; §7 erreurs → T2 nginx + caveat recall_semantic ; §8 sécurité (token séparé, allowlist, rate-limit, logs, :ro, rotation) → T2 ; §9 souveraineté → montage :ro + pas d'API ; §10 transition → hors code (merge existant) ; §11 tests → T1 (pytest) + T2/T3 (smoke) ; §12 étapes root → T3.
- **Placeholders :** `__MEM_READ_TOKEN__` et `<TOKEN>` = secrets instanciés au déploiement (intentionnel), pas des TODO.
- **Cohérence des types/noms :** `build_http_server`/`main_http`/`multiservice-mcp-http`/port `8302`/`MULTISERVICE_HTTP_*` cohérents entre T1, T2, T3.
