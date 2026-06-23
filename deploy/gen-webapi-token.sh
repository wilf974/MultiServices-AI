#!/usr/bin/env bash
# Genere un token API web + l'entree de registre a coller dans webapi-tokens.json.
set -euo pipefail
NAME="${1:?usage: gen-webapi-token.sh <nom> [source]}"
SRC="${2:-project:$NAME}"
TOKEN=$(openssl rand -hex 32)
echo "Token pour $NAME (source=$SRC) :"
echo "  $TOKEN"
echo "Entree a ajouter dans /home/<user>/mem-secrets/webapi-tokens.json :"
echo "  \"$TOKEN\": { \"source\": \"$SRC\" }"
