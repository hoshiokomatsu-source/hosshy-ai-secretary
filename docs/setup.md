# ホッシーくん セットアップ手順（MacBook Air）

## 全体の流れ

```
① Pythonとパッケージをインストール
② リポジトリをクローン
③ .env を設定
④ MCPサーバーを起動
⑤ Cloudflare Tunnel で外部公開
⑥ Claude.ai に登録
```

---

## ① Python 環境を準備する

```bash
# Homebrew がなければ先にインストール
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# Python をインストール
brew install python@3.12

# 確認
python3 --version
```

---

## ② リポジトリをクローン

```bash
git clone https://github.com/hoshiokomatsu-source/hosshy-ai-secretary.git ~/hosshy
cd ~/hosshy/mcp-server
```

---

## ③ パッケージをインストール

```bash
pip3 install -r requirements.txt
playwright install chromium
```

---

## ④ .env を設定

```bash
cp .env.example .env
```

`.env` をテキストエディタで開いて `YOUR_USERNAME` を自分のユーザー名に書き換える。

```
DOWNLOAD_DIR=/Users/（MacBook AirのユーザーID）/Dropbox/komatsu hoshio/Movie Edit/R4/Active
PORT=8000
```

---

## ⑤ MCPサーバーを起動

```bash
cd ~/hosshy/mcp-server
python3 server.py
```

以下のようなログが出れば成功：

```
Streamable HTTP server running on http://127.0.0.1:8000
```

---

## ⑥ Cloudflare Tunnel をインストールして起動

```bash
# cloudflared をインストール
brew install cloudflared

# 別のターミナルで起動（server.py は起動したまま）
cloudflared tunnel --url http://localhost:8000
```

数秒後に以下のようなURLが表示される：

```
https://xxxxxxxx-xxxx-xxxx.trycloudflare.com
```

このURLをメモしておく（起動するたびに変わるので注意）。

---

## ⑦ Claude.ai に登録

1. Claude.ai をブラウザで開く
2. 右上のアイコン → **Settings**
3. **Integrations** → **Add integration**
4. 上記の `https://xxxxxxxx.trycloudflare.com` を入力
5. 保存

これでどこからでも Claude がホッシーくんのツールを使えるようになる。

---

## MacBook Air を常時起動にする

1. システム設定 → バッテリー → 「電源アダプタ接続時にスリープしない」をオン
2. ディスプレイのスリープは許容（画面が暗くなっても処理は続く）

---

## 毎日の起動手順（定着したら自動化する）

```bash
cd ~/hosshy/mcp-server
python3 server.py &
cloudflared tunnel --url http://localhost:8000
```
