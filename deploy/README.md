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
# avec token -> 200 ou 406 selon l'en-tete Accept (le GET nu renvoie 406 : le serveur tourne)
curl -s -o /dev/null -w "%{http_code}\n" -H "Authorization: Bearer <MEM_READ_TOKEN>" https://mem.example.com/mcp
# sans token -> 401
curl -s -o /dev/null -w "%{http_code}\n" https://mem.example.com/mcp
# depuis une IP NON listee -> 403
```

## Rotation du token
Éditer la valeur dans `/etc/nginx/sites-enabled/mem.example.com`, puis
`nginx -t && systemctl reload nginx`, et mettre à jour le header des clients.

## Limite connue (MVP)
`recall_semantic` nécessite Ollama + index, **absents du conteneur MVP**. L'index n'étant
volontairement pas monté (cf. `docker-run-mem.sh`), cet outil **se replie proprement en lexical**.
Les 11 autres outils (lexicaux) fonctionnent pleinement. Sémantique réel = phase 2.
`MEM_WRITE_TOKEN` : réservé, non utilisé (l'écriture distante est phase 2).
