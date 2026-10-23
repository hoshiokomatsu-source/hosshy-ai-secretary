# ホッシーくん（hosshy-ai-secretary）

動画編集者のための AI 秘書。MCP サーバー（`mcp-server/server.py`）を launchd（`com.hossy.server`）で動かし、Claude のカスタムコネクタ「Hossy」から使う。ユーザーとのやりとりは日本語。

## 分担（2026-10-23 に決めたもの）

- ホッシーくんは窓口：受付・ギガファイル便のダウンロード（`downloader.py` / `pipeline.py`）・スプレッドシート転記（`sheets.py`）・freee（`freee*.py`）
- Premiere のセットアップ作業（シーケンス作成・R4自動処理・マスク自動トラッキング・縦横対応）は **R4**（`~/Documents/src/Movie Edit/R4`、別リポジトリ movie-edit-r4）が持つ。中身を変えるときは R4 側を直し、ここは呼び方だけ合わせる
  - `premiere.py` … 素材フォルダを決めて R4 のコマンドを組み立て、終わるまで見守ってホッシーくんの画面（`status.py`）を更新する
  - `r4.py` + `r4_job/` … R4 のコマンドを「ターミナル」で動かす（launchd から動くこのサーバーにはアクセシビリティ・画面収録の許可が無いため）。一度に1つだけ。ログは `/tmp/hossy_r4.log`、結果は `/tmp/hossy_r4_result.json`
- テロップ整形は別のもので、ここには入れない

## 決まりごと

- Premiere が開いていたら Premiere の作業は始めず「閉じてからもう一度」と返す（保存していない作業を消さないため）
- 素材フォルダには .prproj 以外の作業ファイルを残さない
- 時間がかかる作業（ダウンロード、Premiere の作業）はバックグラウンドで動かし、ツールはすぐ返す（Claude はツールを5分しか待たない）。状況は `check_download_status` / `check_premiere_status`
- 素材の映像は公開できない内容を含む。スクリーンショットは UI 部分だけ切り抜く

## 変更したら

```bash
launchctl kickstart -k gui/$(id -u)/com.hossy.server
```

起動には `/tmp/hossy_public_url.txt` が要る（消えていたら `https://hossy.komatour.com` を書く）。再起動後、ユーザーに Claude の Hossy コネクタを再接続してもらう。main に直接コミットする。
