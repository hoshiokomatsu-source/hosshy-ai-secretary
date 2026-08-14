# Mac再起動後の復旧マニュアル

MacBook Airを再起動・アップデートした後、ホッシーくんを再び使えるようにするための手順。
**この4ステップだけでOK。** 上から順にやればよい。

対象読者：ホシさん本人（ターミナルで手を動かす人）

---

## 前提

- 作業場所は `~/hosshy`（`~/src/hossy`ではない。コード編集用と実行用でディレクトリが分かれている）
- ターミナルを2つ開く（① Tunnel用、② サーバー用）

---

## ① Cloudflare Tunnelを起動してURLを確定させる

ターミナル1つ目：

```bash
cloudflared tunnel --url http://localhost:8000
```

しばらくすると以下のような行が表示される。この **URLをメモする**（毎回ランダムに変わる）。

```
https://xxxx-xxxx-xxxx-xxxx.trycloudflare.com
```

このターミナルは閉じずに開いたままにしておく。

---

## ② MCPサーバーを起動する（スリープ対策込み）

ターミナル2つ目：

```bash
cd ~/hosshy && git pull
cd ~/hosshy/mcp-server
caffeinate -dims env DOWNLOAD_DIR="/Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active" PUBLIC_URL="https://（①でメモしたURL）" ~/hosshy/venv/bin/python server.py
```

以下が表示されれば成功：

```
🚀 ホッシーくん起動中... http://0.0.0.0:8000/mcp
🔐 OAuth有効: https://xxxx.trycloudflare.com/mcp をClaudeのコネクタに登録してください
INFO:     Uvicorn running on http://0.0.0.0:8000
```

`caffeinate -dims`を付けることで、このサーバーが動いている間Macが自動スリープしなくなる
（ただしノートパソコンのフタを閉じる「クラムシェルモード」は外部モニター等がないと防げないので、
フタは開けたままにしておくこと）。

このターミナルも閉じずに開いたままにしておく。

---

## ③ Claude.aiのコネクタを登録し直す

Tunnel URLが変わったので、Claude.ai側の登録も更新が必要。**「再接続」ボタンは古いURLの
ままなので使えない。必ず一度削除してから登録し直す。**

1. [claude.ai](https://claude.ai) を開く → 左下の名前 → **設定（Settings）**
2. **コネクタ（Connectors）** を開く
3. 既存の「hossy」コネクタがあれば **削除**
4. 「カスタムコネクタを追加」を選択
5. URL欄に、**末尾に`/mcp`を付けたもの**を入力

   ```
   https://（①でメモしたURL）/mcp
   ```

6. 保存 → 自動でOAuth認可が走り、接続完了になるはず

---

## ④ 動作確認

Claudeのチャットで以下のように送ってみる：

```
ツールが使えるか確認して
```

`download_and_record` / `check_download_status` / `list_downloaded_files` の
3つが見えればOK。実際にギガファイル便のURLを1つ送って、`~/Dropbox/Movie Edit/R4/Active`に
ファイルが増えるか確認できればなお安心。

---

## うまくいかないとき

`docs/handoff.md`の「トラブルシューティング履歴」の表を参照。よくあるのは：

| 症状 | 対処 |
|---|---|
| ポート8000が使用中と言われる | `ps aux \| grep server.py` で既存プロセスがないか確認し、あれば`kill -9`で終了してからやり直す |
| 「再接続」を押しても失敗する | 古いURLに対して再接続しようとしている。コネクタを一度削除してから新規追加し直す |
| Claude側は「エラー」と出るがMacにはファイルが保存されている | 大容量ファイル（数GB〜）は正常な挙動。バックグラウンドで処理が続いているだけなので、少し待って「ダウンロード状況を確認して」と聞けばOK |

---

## 参考：現在の固定情報（変わらないもの）

```
GitHubリポジトリ: git@github.com:hoshiokomatsu-source/hosshy-ai-secretary.git
作業ディレクトリ（実行用）: ~/hosshy
venv: ~/hosshy/venv
DOWNLOAD_DIR: /Users/hoshiokomatsu/Dropbox/Movie Edit/R4/Active
サーバーのポート: 8000
```

再起動のたびに変わるのは **Tunnel URL（`PUBLIC_URL`）だけ**。それ以外はこのまま使い回せる。
