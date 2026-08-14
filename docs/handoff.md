# 引き継ぎ書（MacBook Air Cursor用）

## このプロジェクトは何か

「ホッシーくん」AI秘書。ギガファイル便のリンクをClaudeアプリに送るだけで、
MacBook Airが自動でダウンロード→Googleスプレッドシート転記まで行うシステム。

---

## 現在の状態

### 完了していること
- `mcp-server/` 以下にMCPサーバーのコードを実装済み
  - `server.py` : MCPサーバー本体（Claudeから呼ばれる窓口）
  - `downloader.py` : ギガファイル便をPlaywrightで自動DL
  - `sheets.py` : Google Sheets転記（認証設定はまだ）
  - `requirements.txt` : 必要パッケージ一覧
  - `.env.example` : 設定ファイルのテンプレート

### MacBook Air上での作業状況
- Homebrew インストール済み ✅
- Python 3.12 インストール済み ✅
- リポジトリを `~/hosshy` にクローン済み ✅
- 仮想環境 `~/hosshy/venv` 作成済み ✅
- パッケージインストール済み（`pip install -r requirements.txt`） ✅
- Playwright ブラウザインストール済み ✅
- `.env` ファイル作成済み（`~/hosshy/mcp-server/.env`） ✅

---

## 今やるべきこと（次のステップ）

### ① まず古いPythonプロセスを確実に止める

新しいターミナルを開いて：

```bash
ps aux | grep server.py
```

プロセスが残っていたら：

```bash
kill -9 <表示されたPID番号>
```

### ② 最新コードを取得

```bash
cd ~/hosshy && git pull
```

### ③ uvicorn を追加インストール

```bash
~/hosshy/venv/bin/pip install uvicorn
```

### ④ サーバーを起動

```bash
cd ~/hosshy/mcp-server && ~/hosshy/venv/bin/python server.py
```

**成功すると以下が表示される：**
```
🚀 ホッシーくん起動中... http://0.0.0.0:8000
INFO:     Started server process
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### ⑤ 別タブで動作確認

新しいターミナルタブ（Cmd+T）を開いて：

```bash
curl http://localhost:8000/
```

何かレスポンスが返ってきたらHTTPサーバーとして起動成功。

### ⑥ Cloudflare Tunnel をインストール・起動

```bash
brew install cloudflared
```

```bash
cloudflared tunnel --url http://localhost:8000
```

`https://xxxx.trycloudflare.com` のようなURLが発行されたらメモする。

### ⑦ Claude.ai にMCPサーバーを登録

1. [claude.ai](https://claude.ai) を開く
2. 右上アイコン → Settings → Integrations
3. 「Add integration」→ 上記のURLを入力
4. 保存

### ⑧ テスト

Claudeのチャットで：
> 「ツールが使えるか確認して」

と送ってみて、`download_and_record` や `list_downloaded_files` が認識されればOK。

---

## トラブルシューティング

### `mcp.sse_app()` でAttributeErrorが出た場合

```bash
~/hosshy/venv/bin/python -c "from mcp.server.fastmcp import FastMCP; print(dir(FastMCP))"
```

で利用可能なメソッドを確認して教えてもらう。

### .envのDOWNLOAD_DIRパス

```
/Users/hoshiokomatsu/Dropbox/komatsu hoshio/Movie Edit/R4/Active
```

---

## アーキテクチャ全体像

```
Claudeアプリ（どこからでも）
    ↕ MCP Protocol（HTTP/SSE）
Cloudflare Tunnel（中継）
    ↕
MacBook Air: server.py（port 8000で待ち受け）
    ├── download_and_record(url) → Playwright → DL → Sheets転記
    └── list_downloaded_files()  → フォルダ確認
```

---

## Google Sheets 認証（まだやっていない）

`sheets.py` は実装済みだが、Google Cloud の認証設定が未完了。
`.env` の `SPREADSHEET_ID` が空なら自動スキップされるので、
まずダウンロード部分だけ動かして後から追加する方針でOK。
