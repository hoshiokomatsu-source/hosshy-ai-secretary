#!/bin/bash
# Named Tunnel を作る。komatour.com のネームサーバーは絶対に変えない。
# ムームーDNSに CNAME を1件足すだけで固定URLになる。
set -euo pipefail

if [[ ! -f "$HOME/.cloudflared/cert.pem" ]]; then
  echo "先にブラウザで Cloudflare ログインが必要です:"
  echo "  cloudflared tunnel login"
  echo "（komatour.com を Cloudflare に移す必要はない。アカウントログインだけ）"
  exit 1
fi

if ! cloudflared tunnel list 2>/dev/null | grep -q ' hossy '; then
  cloudflared tunnel create hossy
fi

TUNNEL_ID=$(cloudflared tunnel list | awk '/ hossy / {print $1; exit}')
if [[ -z "$TUNNEL_ID" ]]; then
  echo "tunnel id が取れませんでした" >&2
  exit 1
fi

CREDS="$HOME/.cloudflared/${TUNNEL_ID}.json"
cat > "$HOME/.cloudflared/hossy.yml" <<EOF
tunnel: ${TUNNEL_ID}
credentials-file: ${CREDS}
ingress:
  - hostname: hossy.komatour.com
    service: http://localhost:8000
  - service: http_status:404
EOF

echo
echo "設定を書きました: ~/.cloudflared/hossy.yml"
echo
echo "ムームードメインの DNS に、この1件だけ追加する（ネームサーバーは変えない）:"
echo
echo "  ホスト: hossy"
echo "  種別:   CNAME"
echo "  値:     ${TUNNEL_ID}.cfargotunnel.com"
echo
echo "反映後:"
echo "  launchctl kickstart -k \"gui/\$(id -u)/com.hossy.tunnel\""
echo "  Claude のコネクタを https://hossy.komatour.com/mcp に差し替え"
