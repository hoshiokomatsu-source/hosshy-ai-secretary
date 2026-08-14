# 引き継ぎ書（次のチャット用・2026-08-14 22:06時点）

## このプロジェクトは何か

「ホッシーくん」AI秘書。ギガファイル便のリンクをClaudeアプリに送るだけで、
Macが自動でダウンロード→Googleスプレッドシート転記まで行うシステム。

呼び方：ユーザーのことは「ホシさん」と呼ぶこと。

---

## 重要：作業マシンについて

`~/src/hossy`（Cursorのワークスペース）と `~/hosshy`（ホシさんが手動で
コマンドを打つ場所）は **同じMac（M2Air-of-Hoshi）上の別ディレクトリ** に
ある同じGitHubリポジトリのクローン。別マシンではない。

- コード編集は `~/src/hossy` で行う
- 動作確認・起動は `~/hosshy` を使う（venvもここにある: `~/hosshy/venv`）
- 変更したら `~/src/hossy` で commit & push → `~/hosshy` で `git pull`
- ポート8000を両方で取り合うと "address already in use" になるので注意

GitHubリポジトリ: `git@github.com:hoshiokomatsu-source/hosshy-ai-secretary.git`

---

## 現在の状態（かなり進んだ）

### 完了していること

1. **MCPサーバー本体は実装済み**
   - `mcp-server/server.py` : MCPサーバー本体
   - `mcp-server/oauth_provider.py` : 簡易OAuth2.1プロバイダー（新規実装）
   - `mcp-server/downloader.py` : ギガファイル便をPlaywrightで自動DL
   - `mcp-server/sheets.py` : Google Sheets転記（認証設定はまだ未着手）

2. **Claude.aiの「カスタムコネクタ」がOAuth 2.1必須と判明**
   - OAuthなしでは「サインインサービスに登録できませんでした」と接続失敗する
   - 対策として `oauth_provider.py` に「認可リクエストは全部自動承認する」
     一人用の簡易OAuthプロバイダーを実装済み（ログイン画面なし）
   - `PUBLIC_URL` 環境変数（Cloudflare TunnelのURL）が設定されていれば
     OAuth有効、未設定ならOAuthなしのローカル動作にフォールバックする

3. **エンドポイントはStreamable HTTP方式（`/mcp`）に統一済み**
   - 以前は `/sse`（旧SSE方式）を使っていたが、Claude.aiの最新コネクタは
     `/mcp` パスでのStreamable HTTPを前提にしているため切り替えた
   - `curl` でOAuth登録→認可→トークン取得→`/mcp`への`initialize`呼び出し
     まで一通り動作確認済み（サーバー単体としては正常に動く）

4. **Claude Cowork の Dispatch機能は使えないと判明**
   - Dispatch（スマホ→PC操作）は「リモートMCPコネクタ」経由でないと使えず、
     ローカルの`claude_desktop_config.json`によるstdio方式のMCPサーバーは
     Cowork/Dispatchでは使えない（Claude Desktopの通常チャットでのみ有効）
   - なのでCloudflare Tunnel + OAuthの構成が必須という結論に至った

### 直近でやったこと・今の課題

- Cloudflare Tunnelを起動し、`PUBLIC_URL`にそのURLを設定してサーバーを
  起動 → Claude.aiのコネクタ設定に `https://xxxx.trycloudflare.com/mcp`
  を登録してもらう、というところまで進めた
- 「アカウントは認証されましたが、指定されたURLにMCPサーバーが見つから
  ない」というエラーが出たため `/sse` → `/mcp`（Streamable HTTP）に
  切り替えて再度試している最中（**この結果がまだ確認できていない**）

### 次にやるべきこと

1. ホシさんに、新しいURL（末尾`/mcp`付き）でコネクタ登録を試してもらった
   結果を確認する
2. 繋がったら、Claudeのチャットで「ツールが使えるか確認して」と送り、
   `download_and_record` / `list_downloaded_files` が認識されるか確認
3. 実際にギガファイル便のリンクを送って、ダウンロード→
   `~/Dropbox/Movie Edit/R4/Active` への保存まで動くか確認
4. まだつまずくようなら、サーバーのログ（`uvicorn`の出力）を確認する
5. Google Sheets連携（`sheets.py`）はまだ未設定なので、ダウンロードが
   安定したら着手する

---

## 起動手順（現時点の正しい手順）

### ① プロセスの掃除

```bash
pkill -9 -f server.py
pkill -9 -f 'cloudflared tunnel'
```

### ② 最新コードを取得

```bash
cd ~/hosshy && git pull
```

### ③ Tunnelを先に起動してURLを確定させる

```bash
cloudflared tunnel --url http://localhost:8000
```

`https://xxxx.trycloudflare.com` のようなURLが出るのでメモする。
**このURLは起動のたびに変わる**。

### ④ 別タブで、そのURLを`PUBLIC_URL`にしてサーバー起動

```bash
cd ~/hosshy/mcp-server
DOWNLOAD_DIR="/Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active" \
PUBLIC_URL="https://（③でメモしたURL）" \
~/hosshy/venv/bin/python server.py
```

以下が出れば成功：
```
🚀 ホッシーくん起動中... http://0.0.0.0:8000/mcp
🔐 OAuth有効: https://xxxx.trycloudflare.com/mcp をClaudeのコネクタに登録してください
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### ⑤ Claude.aiにコネクタ登録

1. [claude.ai](https://claude.ai) → 左下の名前 → Settings → **コネクタ**
2. 「追加」→「カスタムコネクタを追加」
3. URLは **`/mcp`を末尾に付けたもの** を入力

```
https://（③のURL）/mcp
```

4. 保存 → 自動的にOAuth認可が完了して接続されるはず

### ⑥ テスト

Claudeのチャットで「ツールが使えるか確認して」と送り、
`download_and_record` / `list_downloaded_files` が見えればOK。

---

## `.env` の設定値

`~/hosshy/mcp-server/.env` に以下が入っている（`DOWNLOAD_DIR`のパスに注意、
`komatsu hoshio`は不要。Dropboxのシンボリックリンクが既にそこを指している）：

```
DOWNLOAD_DIR=/Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active
PORT=8000
SPREADSHEET_ID=your_spreadsheet_id_here   ← 未設定
GOOGLE_CREDENTIALS_PATH=/Users/hoshiokomatsu/.config/hosshy/credentials.json  ← 未設定
```

`PUBLIC_URL`は`.env`には書かず、起動時に環境変数として毎回渡す方式に
している（Tunnel URLが毎回変わるため）。

---

## トラブルシューティング履歴（同じ轍を踏まないために）

| 症状 | 原因 | 対策 |
|---|---|---|
| ポート8000 "address already in use" | `~/src/hossy`と`~/hosshy`で二重にサーバー起動していた | 起動前に`ps aux \| grep server.py`で確認 |
| Tunnel経由アクセスでサーバーが丸ごと落ちる | MCPのDNS rebinding protectionがCloudflareのHostヘッダーを拒否 | `TransportSecuritySettings(enable_dns_rebinding_protection=False)`を設定済み |
| 「サインインサービスに登録できませんでした」 | Claude.aiのコネクタはOAuth必須。サーバー未実装だった | `oauth_provider.py`で簡易OAuthを実装済み |
| 「MCPサーバーが見つからない」（OAuth認証は成功） | `/sse`（旧SSE方式）にURLを向けていたが、最新コネクタは`/mcp`（Streamable HTTP）を要求 | `mcp.streamable_http_app()`に切り替え済み。URLは末尾`/mcp`必須 |
| Claude Desktopの`claude_desktop_config.json`にMCPサーバーを直接書けば楽では? | ローカルstdio方式はCowork/Dispatchでは使えない（通常のClaude Desktopチャットのみ対応） | 使わない方針に確定 |

---

## アーキテクチャ全体像（現状）

```
スマホ/PCのClaude.ai（コネクタ経由）
    ↕ OAuth 2.1 + Streamable HTTP（/mcp）
Cloudflare Tunnel（毎回URLが変わる quick tunnel）
    ↕
Mac: server.py（port 8000で待ち受け、oauth_provider.pyで自動承認）
    ├── download_and_record(url) → Playwright → DL → Sheets転記（Sheetsは未設定）
    └── list_downloaded_files()  → フォルダ確認
```

### 既知の制約・今後の課題

- Cloudflare quick tunnelはURLが毎回変わるため、再起動のたびにClaude.ai
  側のコネクタURLも登録し直す必要がある。将来的には固定ドメインの
  Named Tunnelへの移行を検討する余地あり
- OAuthは「誰でも自動承認」という単純な実装なので、Tunnel URLが漏れると
  誰でもアクセスできてしまう（個人利用前提として許容している）
- Google Sheets連携は未着手
