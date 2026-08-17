#!/bin/bash
# MCPサーバーだけを起動する。Tunnelは触らない。
set -euo pipefail

DOWNLOAD_DIR="${DOWNLOAD_DIR:-/Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active}"
PYTHON="${HOSSY_PYTHON:-/Users/hoshiokomatsu/hosshy/venv/bin/python}"
SERVER_DIR="${HOSSY_SERVER_DIR:-/Users/hoshiokomatsu/hosshy/mcp-server}"
URL_FILE="/tmp/hossy_public_url.txt"

PUBLIC_URL=""
for _ in $(seq 1 30); do
  if [[ -f "$URL_FILE" ]]; then
    PUBLIC_URL=$(cat "$URL_FILE")
    if [[ -n "$PUBLIC_URL" ]]; then
      break
    fi
  fi
  sleep 1
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "PUBLIC_URL がありません。Tunnelが先に起動しているか確認してください。" >&2
  exit 1
fi

echo "Using PUBLIC_URL=$PUBLIC_URL"
cd "$SERVER_DIR"
exec caffeinate -dims env DOWNLOAD_DIR="$DOWNLOAD_DIR" PUBLIC_URL="$PUBLIC_URL" "$PYTHON" server.py
