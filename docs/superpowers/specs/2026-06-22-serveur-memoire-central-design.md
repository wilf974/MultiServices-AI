# Design — Serveur de mémoire central (MVP lecture seule, HTTPS)

> Date : 2026-06-22 · Projet : MultiService IA · Statut : approuvé (architecture), en revue (spec)
> Sessions liées : `deploiement-vps-mcp`. S'inscrit dans la « 2e surface cloud » déjà
> inscrite à la feuille de route (décision `d9d7e19c`, session `suite-observation`).

## 1. Problème & objectif

Aujourd'hui la mémoire (journal append-only) existe en plusieurs copies (machine maison Windows,
VM Linux) réconciliées par un merge bidirectionnel. Pour donner accès à des **postes sur des
réseaux différents** (ex. poste de travail), copier le journal partout est risqué (divergence,
surface sensible dupliquée) et contraire à la souveraineté.

**Objectif** : exposer la mémoire comme un **serveur central unique** sur la VM, interrogeable à
distance en **HTTPS avec token**, sans qu'aucun poste client ne détienne de copie du journal.

**Ce MVP = LECTURE SEULE.** L'écriture distante (ingest authentifié) est explicitement reportée
à un sprint ultérieur (phase 2).

## 2. Objectifs / Non-objectifs

**Objectifs (MVP)**
- Exposer les 12 outils MCP **lecture seule** existants via HTTPS.
- Accès par **bearer token de lecture** (`MEM_READ_TOKEN`) + **allowlist IP**, derrière nginx.
- Le journal de la VM devient la **source de vérité centrale** ; lecture seule garantie par l'infra
  (montage Docker `:ro`).
- N'importe quel poste (réseau quelconque, IP allowlistée) se connecte via `claude mcp add
  --transport http`.

**Non-objectifs (reportés)**
- Écriture / ingest distant (phase 2). Mais le **token de lecture est séparé dès maintenant** pour
  ne pas casser le modèle de sécurité plus tard (`MEM_WRITE_TOKEN` réservé, non utilisé).
- mTLS (phase 2+), permissions par source/projet (phase 3), sémantique servie côté serveur,
  multi-token par utilisateur.

## 3. Architecture

```
poste client (IP allowlistée, n'importe quel réseau)
   │  claude mcp add --transport http https://mem.example.com/mcp
   │  Authorization: Bearer <MEM_READ_TOKEN>
   ▼
nginx :443 (mem.example.com)  ── TLS (certbot)
   │  allow <IP_PUBLIQUE_MAISON>; allow <IP_PUBLIQUE_BUREAU>; deny all;
   │  vérif Bearer MEM_READ_TOKEN ; limit_req ; access_log dédié
   ▼  proxy_pass http://127.0.0.1:8302  (proxy_buffering off, read_timeout long pour SSE)
conteneur Docker : multiservice MCP (FastMCP, transport streamable-http, 0.0.0.0:8302)
   ▼  volume monté en LECTURE SEULE (:ro)
/home/<user>/.aethercore/journal-llm.jsonl   = source de vérité centrale
```

**Trois barrières complémentaires** : (1) nginx protège l'accès ; (2) Docker isole le runtime ;
(3) le montage `:ro` garantit *au niveau OS* que le serveur ne peut pas écrire le journal — la
promesse constitutionnelle « surface MCP en lecture seule » (D5) devient une garantie d'infra.

**DNS** : `mem.example.com` → A `<IP_PUBLIQUE_MAISON>`, TTL 300 (IP publique du site ; la VM <VPS_LAN>
est derrière, port-forward 80/443 existant).

## 4. Composants & fichiers

### Code (dans le repo, testé par pytest)
- `multiservice/mcp_server.py` : ajouter un lancement **streamable-http** réutilisant le
  `build_server()` existant. **Aucun nouvel outil** ; les 12 outils lecture seule sont inchangés.
  Hôte/port lus depuis l'env (`MULTISERVICE_HTTP_HOST` défaut `0.0.0.0`, `MULTISERVICE_HTTP_PORT`
  défaut `8302`).
- Point d'entrée console `multiservice-mcp-http` dans `pyproject.toml` (`[project.scripts]`) — pas
  de flag ambigu, comme `multiservice-mcp` l'a fait pour contourner le bug `-m` de `claude mcp add`.
- `tests/test_mcp_http.py` : **test de régression permanent** (règle projet) :
  - le serveur http se construit sans erreur ;
  - l'ensemble des outils exposés en http == celui exposé en stdio (parité) ;
  - **aucun outil n'écrit** le journal (lecture seule — vérif structurelle).

### Infra (étapes root ; fichiers fournis dans `deploy/`)
- `deploy/Dockerfile.mem` : `python:3.13-slim`, install `.[mcp]`, `CMD` = `multiservice-mcp-http`
  bindé `0.0.0.0:8302` dans le conteneur.
- `deploy/docker-run-mem.sh` :
  `docker run -d --name mem-mcp --restart unless-stopped -p 127.0.0.1:8302:8302 \
   -v /home/<user>/.aethercore:/data:ro -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl mem-mcp`
- `deploy/mem.example.com.nginx` : site nginx (voir §6).

## 5. Flux & contrat client

Le transport **streamable-http** de FastMCP expose l'endpoint sur `/mcp`. Côté client :
```
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp \
  --header "Authorization: Bearer <MEM_READ_TOKEN>"
```
Vérif : `claude mcp list` → `multiservice-memory ... ✔ connected`. Les outils (`recent`, `brief`,
`recall`, `why`, `replay`, `replay_event`, `forecast`, `usage`, `reasoning`, `lessons`,
`recall_semantic`, `index_status`) répondent comme en stdio.

## 6. nginx — cœur de la sécurité (modèle)

```nginx
map $http_authorization $mem_ok { default 0; "Bearer <MEM_READ_TOKEN>" 1; }
limit_req_zone $binary_remote_addr zone=mem:10m rate=30r/m;

server {
  listen 443 ssl;
  server_name mem.example.com;        # ssl_certificate via certbot

  allow <IP_PUBLIQUE_MAISON>;                 # maison / IP publique
  allow <IP_PUBLIQUE_BUREAU>;               # bureau
  deny all;

  access_log /var/log/nginx/mem.access.log;

  location /mcp {
    if ($mem_ok = 0) { return 401; }
    limit_req zone=mem burst=10 nodelay;
    proxy_pass http://127.0.0.1:8302;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_buffering off;              # streamable-http / SSE
    proxy_read_timeout 1h;
  }
}
# server :80 -> redirect 443 (certbot)
```

## 7. Gestion d'erreurs

| Cas | Réponse | Où |
|---|---|---|
| IP hors allowlist | 403 | nginx |
| Token absent/faux | 401 | nginx |
| Trop de requêtes | 429 | nginx |
| Conteneur arrêté | 502 | nginx ; `--restart unless-stopped` relance |
| `recall_semantic` sans Ollama dans le conteneur | **À encadrer en implémentation** : le conteneur MVP n'a pas Ollama. Le code replie en lexical quand l'index manque, mais pas garanti si l'embedder est injoignable → décider en impl. (repli lexical forcé en mode http, OU outil masqué). Les 11 autres outils (lexicaux) ne sont pas concernés. |
| Ligne de journal corrompue | tolérée (lecture robuste existante) |

## 8. Sécurité (exigences retenues)

- **HTTPS only** (80 → 443).
- **Allowlist IP** : `<IP_PUBLIQUE_MAISON>`, `<IP_PUBLIQUE_BUREAU>` (extensible).
- **`MEM_READ_TOKEN`** fort (≥ 32 octets aléatoires) ; stocké uniquement dans nginx + config client.
- **Rate-limit** (`limit_req`) + **access log dédié**.
- **Montage `:ro`** : lecture seule garantie par l'OS, même si le code bugge.
- **Rotation** documentée : éditer la valeur du token dans nginx → `nginx -t && systemctl reload nginx`.
- **`MEM_WRITE_TOKEN` réservé** (déclaré, non utilisé) pour ne pas casser le modèle en phase 2.

## 9. Souveraineté

Le journal **reste uniquement sur la VM** ; les postes clients n'en détiennent **aucune copie**.
Inférence/embeddings restent locaux (aucune API hébergée). Conforme C1-C6 + D5.

## 10. Transition & écritures en phase 1

Avant l'ingest distant (phase 2), le serveur lit le **journal de la VM** (= central). La machine
maison continue d'écrire en local puis pousse ses events dans la VM via `sync_memory_merge.ps1`
(merge bidirectionnel par `id`, déjà livré). Aucun travail gaspillé : le merge reste le pont
maison → centre jusqu'à la phase 2.

## 11. Tests & vérification

- **pytest** : `tests/test_mcp_http.py` (construction, parité d'outils, lecture seule).
- **Smoke post-déploiement** (checklist manuelle) :
  - `curl -H "Authorization: Bearer <TOKEN>" https://mem.example.com/mcp` (depuis IP allowlistée) → 200/handshake ;
  - sans header → **401** ; depuis IP non listée → **403** ;
  - `claude mcp add --transport http ...` sur un poste → `claude mcp list` = connected.

## 12. Étapes root (l'utilisateur exécute ; fichiers/commandes fournis)

1. DNS `mem.example.com` A → <IP_PUBLIQUE_MAISON> (TTL 300). *(fait par l'utilisateur)*
2. `docker build -f deploy/Dockerfile.mem -t mem-mcp .` puis `deploy/docker-run-mem.sh`.
3. Site nginx `deploy/mem.example.com.nginx` → `/etc/nginx/sites-enabled/`, certbot, `nginx -t && reload`.
4. Générer `MEM_READ_TOKEN`, l'injecter dans nginx, le distribuer aux postes.

## 13. Phases ultérieures (hors ce spec)

- **Phase 2** : endpoint d'**ingest authentifié** (`MEM_WRITE_TOKEN`, validation stricte
  `AetherEvent`, provenance C2), `memlog`-over-HTTP ; mTLS optionnel ; logs détaillés ; rotation.
- **Phase 3** : permissions par source/projet (`project:aethercore`, `project:multiservice`, …).

## 14. Risques & mitigations

| Risque | Mitigation |
|---|---|
| Fuite du token de lecture | allowlist IP (2e barrière) + rotation + rate-limit + logs |
| SPOF (VM down) | sauvegardes O1b (`backup.py`) + le merge garde une copie maison |
| Latence réseau vs lecture locale | acceptable pour usage interactif |
| Hairpin NAT (poste maison) | egress vu = <IP_PUBLIQUE_MAISON>, déjà allowlisté |
```
