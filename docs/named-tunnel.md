# Tunnel URL を固定する（ネームサーバーは触らない）

`komatour.com` のメール（ムームー / ロリポップ MX）は今のまま。
Cloudflare にドメインを移さない。

## やること

1. ターミナルで `cloudflared tunnel login`（ブラウザで Cloudflare アカウント承認）
2. `~/hosshy/scripts/setup-named-tunnel.sh` を実行
3. ムームーDNSに CNAME を1件追加

```
ホスト: hossy
種別:   CNAME
値:     （スクリプトが表示する xxxxxxxx.cfargotunnel.com）
```

4. Tunnel ジョブを再起動し、Claude のコネクタを
   `https://hossy.komatour.com/mcp` に差し替える

これ以降 URL は変わらない。
