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
