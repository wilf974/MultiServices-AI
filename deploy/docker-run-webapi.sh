#!/usr/bin/env bash
# API REST web (LLM web) : journal RW, registre tokens :ro (hors ~/.aethercore). Central-only.
set -euo pipefail
docker rm -f mem-api 2>/dev/null || true
docker run -d --name mem-api --restart unless-stopped \
  -p 127.0.0.1:8304:8304 \
  -v "$HOME/.aethercore":/data \
  -v "${MEM_SECRETS_DIR:-$HOME/mem-secrets}":/secrets:ro \
  -e MULTISERVICE_JOURNAL=/data/journal-llm.jsonl \
  -e MULTISERVICE_WEBAPI_TOKENS=/secrets/webapi-tokens.json \
  -e MULTISERVICE_WEBAPI_ENABLE=1 \
  -e MULTISERVICE_WEBAPI_PUBLIC_URL="${MEM_PUBLIC_URL:-https://api-mem.example.com}" \
  -e MULTISERVICE_WEBAPI_HOST=0.0.0.0 -e MULTISERVICE_WEBAPI_PORT=8304 \
  mem-api
echo "mem-api lance sur 127.0.0.1:8304 (journal RW, tokens :ro)"
