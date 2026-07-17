#!/usr/bin/env bash
# Genere (si absent) la CA dediee mem-ingest, puis un cert CLIENT pour un CN donne + une cle HMAC.
# Usage : bash gen-mtls.sh <CN> [<source>]   ex: bash gen-mtls.sh bureau project:bureau
set -euo pipefail
CN="${1:?usage: gen-mtls.sh <CN> [source]}"
SRC="${2:-project:$CN}"
CADIR="/etc/nginx/mtls/mem"
SECRETS="${MEM_SECRETS_DIR:-$HOME/mem-secrets}"   # lance en root : exporter MEM_SECRETS_DIR=/home/<compte>/mem-secrets
OUT="$SECRETS/clients/$CN"
mkdir -p "$CADIR" "$OUT"

if [ ! -f "$CADIR/ca.crt" ]; then
  openssl genrsa -out "$CADIR/ca.key" 4096
  openssl req -x509 -new -nodes -key "$CADIR/ca.key" -sha256 -days 3650 \
    -subj "/CN=mem-ingest-CA" -out "$CADIR/ca.crt"
  echo "CA creee : $CADIR/ca.crt"
fi

openssl genrsa -out "$OUT/client.key" 2048
openssl req -new -key "$OUT/client.key" -subj "/CN=$CN" -out "$OUT/client.csr"
openssl x509 -req -in "$OUT/client.csr" -CA "$CADIR/ca.crt" -CAkey "$CADIR/ca.key" \
  -CAcreateserial -days 825 -sha256 -out "$OUT/client.crt"
rm -f "$OUT/client.csr"

HMAC=$(openssl rand -hex 32)
echo "$HMAC" > "$OUT/hmac.key"
echo "--- Cert client + cle HMAC dans $OUT ---"
echo "Entree registre a ajouter dans $SECRETS/ingest-clients.json :"
echo "  \"$CN\": { \"source\": \"$SRC\", \"hmac_key\": \"$HMAC\" }"
