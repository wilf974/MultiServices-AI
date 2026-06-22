#!/usr/bin/env bash
# Conteneur d'ingest distant : journal RW (append d'evenements), registre des cles HMAC :ro.
# Le registre vit HORS de ~/.aethercore pour ne JAMAIS etre lisible par le conteneur de lecture (:ro).
set -euo pipefail
docker rm -f mem-ingest 2>/dev/null || true
docker run -d --name mem-ingest --restart unless-stopped \
  -p 127.0.0.1:8303:8303 \
  -v /home/adminvps/.aethercore:/data \
  -v /home/adminvps/mem-secrets:/secrets:ro \
  -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl \
  -e MULTISERVICE_INGEST_NONCES=/data/ingest-nonces.jsonl \
  -e MULTISERVICE_INGEST_REGISTRY=/secrets/ingest-clients.json \
  -e MULTISERVICE_INGEST_HOST=0.0.0.0 -e MULTISERVICE_INGEST_PORT=8303 \
  mem-ingest
echo "mem-ingest lance sur 127.0.0.1:8303 (journal RW, registre :ro)"
