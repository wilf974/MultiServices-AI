# Déploiement — serveur de mémoire central (mem.example.com)

> MVP **lecture seule**. Conteneur Docker (journal monté `:ro`) derrière nginx
> (`8443 ssl proxy_protocol`), TLS + allowlist IP + bearer token + rate-limit.
> Spec : `docs/superpowers/specs/2026-06-22-serveur-memoire-central-design.md`.

## Architecture du VPS (à connaître)
Un bloc `stream` nginx écoute le **443 public** et route par SNI vers les vhosts http en
**`listen 8443 ssl proxy_protocol`**. `set_real_ip_from 127.0.0.1` + `real_ip_header proxy_protocol`
sont **globaux** dans `nginx.conf` → dans le vhost, `$remote_addr` = la **vraie IP client**
(l'allowlist IP fonctionne donc directement). Un vhost en `listen 443 ssl` n'est **jamais** servi
publiquement (cert par défaut → `curl exit 60`).

## 1. DNS (utilisateur)
`mem.example.com` → A `<IP_PUBLIQUE_MAISON>`, TTL 300. Vérifier qu'il résout avant certbot.

## 2. Code sur le VPS (dépôt public)
```bash
cd /opt/apps && rm -rf mem-mcp-src     # ou ~/mem-mcp-src si pas root sur /opt/apps
git clone -b feature/serveur-memoire-central https://github.com/wilf974/MultiServices-AI.git mem-mcp-src
cd mem-mcp-src
```

## 3. Image + conteneur (Docker accessible sans root si dans le groupe docker)
```bash
docker build -f deploy/Dockerfile.mem -t mem-mcp .
bash deploy/docker-run-mem.sh           # journal :ro + MULTISERVICE_HTTP_ALLOWED_HOSTS
docker ps --filter name=mem-mcp
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: mem.example.com" http://127.0.0.1:8302/mcp  # 406 = up
```

## 4. Certificat TLS (root)
> Si shell root via `su` : `export PATH=$PATH:/usr/sbin:/sbin` (sinon `nginx`/`certbot` ne trouvent pas le binaire). Préférer `sudo -i` / `su -`.
```bash
# bloc HTTP temporaire pour le challenge, puis cert
printf 'server {\n  listen 80;\n  server_name mem.example.com;\n  location / { return 404; }\n}\n' \
  > /etc/nginx/sites-enabled/mem.example.com
nginx -t && systemctl reload nginx
certbot --nginx -d mem.example.com
```

## 5. Token + vhost définitif (root)
```bash
MEM_READ_TOKEN=$(openssl rand -hex 32); echo "TOKEN A NOTER -> $MEM_READ_TOKEN"
sed "s/__MEM_READ_TOKEN__/$MEM_READ_TOKEN/" deploy/mem.example.com.nginx \
  > /etc/nginx/sites-enabled/mem.example.com
nginx -t && systemctl reload nginx
```
Le vhost écoute en `8443 ssl proxy_protocol`, exige `map_hash_bucket_size 128` (token long),
et autorise `<IP_PUBLIQUE_MAISON>` / `<IP_PUBLIQUE_BUREAU>` / `<GW_LAN>` (passerelle LAN via hairpin).

## 6. Brancher un poste client (n'importe où, IP allowlistée)
```bash
# si une ancienne entree existe deja : claude mcp remove multiservice-memory
claude mcp add --transport http multiservice-memory https://mem.example.com/mcp \
  --header "Authorization: Bearer <MEM_READ_TOKEN>"
claude mcp list    # -> multiservice-memory ... connected
```

## Smoke tests (depuis une IP allowlistée)
```bash
TOKEN=<MEM_READ_TOKEN>
# handshake MCP -> 200
curl -s -o /dev/null -w "%{http_code}\n" --http1.1 -X POST \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"x","version":"0"}}}' \
  https://mem.example.com/mcp
curl -s -o /dev/null -w "%{http_code}\n" https://mem.example.com/mcp   # sans token -> 401
```

## Rotation du token
Éditer la valeur dans `/etc/nginx/sites-enabled/mem.example.com`, puis
`nginx -t && systemctl reload nginx`, et mettre à jour le header des clients.

## Pièges rencontrés (résolus)
- **`listen 443` ne marche pas** → utiliser `8443 ssl proxy_protocol` (cf. archi ci-dessus).
- **`nginx: command not found`** en root → `su` sans `-` : `/usr/sbin` absent du PATH.
- **`could not build map_hash`** → `map_hash_bucket_size 128` (clé `Bearer <token>` trop longue).
- **`421` côté client** → protection anti-DNS-rebinding du SDK MCP : le serveur n'accepte que les
  Host de `MULTISERVICE_HTTP_ALLOWED_HOSTS` (posé par `docker-run-mem.sh`). Le Host envoyé par nginx
  (`mem.example.com`) doit y figurer.
- **Depuis le LAN du VPS** : hairpin NAT → nginx voit `<GW_LAN>` (d'où l'allow).

## Limite connue (MVP)
`recall_semantic` se replie en lexical (pas d'Ollama dans le conteneur ; index non monté). Les 11
autres outils fonctionnent. Sémantique réel = phase 2. `MEM_WRITE_TOKEN` : réservé, non utilisé
(écriture distante = phase 2).
