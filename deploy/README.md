# Déploiement — serveur de mémoire central (mem.woutils.com)

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
`mem.woutils.com` → A `82.64.87.227`, TTL 300. Vérifier qu'il résout avant certbot.

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
curl -s -o /dev/null -w "%{http_code}\n" -H "Host: mem.woutils.com" http://127.0.0.1:8302/mcp  # 406 = up
```

## 4. Certificat TLS (root)
> Si shell root via `su` : `export PATH=$PATH:/usr/sbin:/sbin` (sinon `nginx`/`certbot` ne trouvent pas le binaire). Préférer `sudo -i` / `su -`.
```bash
# bloc HTTP temporaire pour le challenge, puis cert
printf 'server {\n  listen 80;\n  server_name mem.woutils.com;\n  location / { return 404; }\n}\n' \
  > /etc/nginx/sites-enabled/mem.woutils.com
nginx -t && systemctl reload nginx
certbot --nginx -d mem.woutils.com
```

## 5. Token + vhost définitif (root)
```bash
MEM_READ_TOKEN=$(openssl rand -hex 32); echo "TOKEN A NOTER -> $MEM_READ_TOKEN"
sed "s/__MEM_READ_TOKEN__/$MEM_READ_TOKEN/" deploy/mem.woutils.com.nginx \
  > /etc/nginx/sites-enabled/mem.woutils.com
nginx -t && systemctl reload nginx
```
Le vhost écoute en `8443 ssl proxy_protocol`, exige `map_hash_bucket_size 128` (token long),
et autorise `82.64.87.227` / `193.252.56.212` / `192.168.1.254` (passerelle LAN via hairpin).

## 6. Brancher un poste client (n'importe où, IP allowlistée)
```bash
# si une ancienne entree existe deja : claude mcp remove multiservice-memory
claude mcp add --transport http multiservice-memory https://mem.woutils.com/mcp \
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
  https://mem.woutils.com/mcp
curl -s -o /dev/null -w "%{http_code}\n" https://mem.woutils.com/mcp   # sans token -> 401
```

## Rotation du token
Éditer la valeur dans `/etc/nginx/sites-enabled/mem.woutils.com`, puis
`nginx -t && systemctl reload nginx`, et mettre à jour le header des clients.

## Pièges rencontrés (résolus)
- **`listen 443` ne marche pas** → utiliser `8443 ssl proxy_protocol` (cf. archi ci-dessus).
- **`nginx: command not found`** en root → `su` sans `-` : `/usr/sbin` absent du PATH.
- **`could not build map_hash`** → `map_hash_bucket_size 128` (clé `Bearer <token>` trop longue).
- **`421` côté client** → protection anti-DNS-rebinding du SDK MCP : le serveur n'accepte que les
  Host de `MULTISERVICE_HTTP_ALLOWED_HOSTS` (posé par `docker-run-mem.sh`). Le Host envoyé par nginx
  (`mem.woutils.com`) doit y figurer.
- **Depuis le LAN du VPS** : hairpin NAT → nginx voit `192.168.1.254` (d'où l'allow).

## Limite connue (MVP)
`recall_semantic` se replie en lexical (pas d'Ollama dans le conteneur ; index non monté). Les 11
autres outils fonctionnent. Sémantique réel = phase 2. `MEM_WRITE_TOKEN` : réservé, non utilisé
(écriture distante = phase 2).

## Écriture distante (ingest mTLS) — phase 2

1. **CA + cert client + clé HMAC** (root) :
   ```bash
   bash /home/adminvps/mem-mcp-src/deploy/gen-mtls.sh bureau project:bureau
   # ajouter l'entree imprimee dans /home/adminvps/mem-secrets/ingest-clients.json
   ```
2. **Conteneur d'ingest** :
   ```bash
   cd /home/adminvps/mem-mcp-src
   docker build -f deploy/Dockerfile.ingest -t mem-ingest .
   bash deploy/docker-run-ingest.sh
   ```
3. **nginx** : appliquer les ajouts mTLS + `location /ingest` du vhost, `nginx -t && systemctl reload nginx`.
4. **Poste client** : copier `client.crt`, `client.key`, `hmac.key`, puis :
   ```bash
   export MEM_INGEST_URL=https://mem.woutils.com/ingest
   export MEM_CLIENT_CERT=/chemin/client.crt MEM_CLIENT_KEY=/chemin/client.key
   export MEM_HMAC_KEY=$(cat /chemin/hmac.key)
   memlog-http "ma decision depuis le bureau" --kind decision --session bureau
   ```
   (le serveur impose `source=project:bureau` via le CN du certificat.)

> Le registre (`ingest-clients.json`) et les clés vivent dans `/home/adminvps/mem-secrets/`,
> **hors** de `~/.aethercore` : le conteneur de lecture (`:ro`) ne peut pas les lire.
