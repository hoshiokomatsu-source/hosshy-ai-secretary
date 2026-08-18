#!/bin/bash
# Cloudflare Tunnel だけを起動する。サーバー再起動では殺さない。
# ~/.cloudflared/hossy.yml があれば固定ドメイン、なければ Quick Tunnel。
set -euo pipefail

TUNNEL_LOG="/tmp/hossy_tunnel.log"
URL_FILE="/tmp/hossy_public_url.txt"
NAMED_CONFIG="${HOME}/.cloudflared/hossy.yml"

if [[ -f "$NAMED_CONFIG" ]]; then
  echo "https://hossy.komatour.com" > "$URL_FILE"
  echo "Named Tunnel: https://hossy.komatour.com"
  exec cloudflared tunnel --config "$NAMED_CONFIG" run
fi

if pgrep -f "cloudflared tunnel --url http://localhost:8000" >/dev/null; then
  echo "Tunnel already running"
  if [[ -f "$URL_FILE" ]]; then
    echo "URL: $(cat "$URL_FILE")"
  fi
  # 既存プロセスが死ぬまで待ってから立て直す（二重起動しない）
  while pgrep -f "cloudflared tunnel --url http://localhost:8000" >/dev/null; do
    sleep 10
  done
fi

: > "$TUNNEL_LOG"
cloudflared tunnel --url http://localhost:8000 >> "$TUNNEL_LOG" 2>&1 &
TUNNEL_PID=$!

PUBLIC_URL=""
for _ in $(seq 1 40); do
  PUBLIC_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -1 || true)
  if [[ -n "$PUBLIC_URL" ]]; then
    break
  fi
  sleep 1
done

if [[ -z "$PUBLIC_URL" ]]; then
  echo "Tunnel URL の取得に失敗しました。" >&2
  exit 1
fi

echo "$PUBLIC_URL" > "$URL_FILE"
echo "Tunnel URL: $PUBLIC_URL"
wait "$TUNNEL_PID"
