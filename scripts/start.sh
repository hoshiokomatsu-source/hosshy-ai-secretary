#!/bin/bash
# ホッシーくん常時起動スクリプト
# Cursorに依存せず、launchd または手動実行で使う。
set -euo pipefail

DOWNLOAD_DIR="${DOWNLOAD_DIR:-/Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active}"
PYTHON="${HOSSY_PYTHON:-/Users/hoshiokomatsu/hosshy/venv/bin/python}"
SERVER_DIR="${HOSSY_SERVER_DIR:-/Users/hoshiokomatsu/hosshy/mcp-server}"
TUNNEL_LOG="/tmp/hossy_tunnel.log"
URL_FILE="/tmp/hossy_public_url.txt"

cleanup() {
  if [[ -n "${TUNNEL_PID:-}" ]]; then
    kill "$TUNNEL_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

PUBLIC_URL=""
if pgrep -f "cloudflared tunnel --url http://localhost:8000" >/dev/null && [[ -f "$URL_FILE" ]]; then
  PUBLIC_URL=$(cat "$URL_FILE")
fi

if [[ -z "$PUBLIC_URL" ]]; then
  : > "$TUNNEL_LOG"
  cloudflared tunnel --url http://localhost:8000 >> "$TUNNEL_LOG" 2>&1 &
  TUNNEL_PID=$!

  for _ in $(seq 1 40); do
    PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)
    if [[ -n "$PUBLIC_URL" ]]; then
      break
    fi
    sleep 1
  done
fi

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Tunnel URL の取得に失敗しました。$TUNNEL_LOG を確認してください。" >&2
  exit 1
fi

echo "$PUBLIC_URL" > "$URL_FILE"
echo "Tunnel URL: $PUBLIC_URL"
echo "Claudeコネクタ登録URL: ${PUBLIC_URL}/mcp"

cd "$SERVER_DIR"
exec caffeinate -dims env DOWNLOAD_DIR="$DOWNLOAD_DIR" PUBLIC_URL="$PUBLIC_URL" "$PYTHON" server.py
