# AI秘書「ホッシーくん」

> 動画編集スタートまでの面倒な事務作業が、1メッセージで解決。

## 概要

チャットにリンクを送るだけで、動画ダウンロード・ファイル整理・スプレッドシート転記・Premiere Proシーケンス作成まで全自動化するシステム。

帰宅時には「すぐ編集できる状態」を実現する。

## キャラクター

**ホッシーくん** — 「お仕事なんでも欲しがり」の *ほし* と、制作者の名前 *ホシ* をかけた名前。  
Mac Studio専用モニターに常駐し、作業状態に応じてスプライトアニメーションが変化する。

## システム構成

```
音声入力（自宅）  ─┐
                    ├─▶ Claude AI ─▶ MCPサーバー（Mac Studio）─▶ DL＋整理
Claudeアプリ（外出）┘                                          ─▶ スプシ転記
                                                               ─▶ Premiere自動化
                                                               ─▶ ホッシーくんUI
```

## ホッシーくんと R4 の分担（2026-10-23）

- **ホッシーくん**（このリポジトリ）は窓口：受付・ギガファイル便のダウンロード・スプレッドシート転記・freee
- **R4**（`~/Documents/src/Movie Edit/R4`、GitHub の movie-edit-r4）は Premiere のセットアップ作業すべて：シーケンス作成・R4自動処理（⌘6・調整レイヤー3つ・Lumetri自動・オーディオゲイン）・マスク自動トラッキング・縦横対応

Premiere の作業のツールは、R4 のコマンドを「ターミナル」で動かして（`mcp-server/r4.py`）、終わるまで見守るだけ。どれも時間がかかるのでバックグラウンドで動き、状況は `check_premiere_status` で聞く。

| ツール | 呼ぶ R4 のコマンド |
|---|---|
| `prepare_premiere`（横 1920×1080。ダウンロードのあとにも自動で動く） | `シーケンス作成/make_project.py <フォルダ> --orientation 横 --quit` |
| `prepare_premiere_mixed`（縦横対応。「例外」なら同期しない） | `シーケンス作成/make_project.py <フォルダ> --quit [--exception]` |
| `mask_tracking`（2周目は V2 の素材のマスク） | `マスク自動トラッキング/track_masks.py run [--track 2]` |

Premiere が開いているときは何もせず「閉じてからもう一度」と返す。素材フォルダには .prproj 以外の作業ファイルを残さない。

## 実装ロードマップ

| フェーズ | 内容 | 技術 |
|---|---|---|
| Phase 1 | 自動DL＋ファイル整理 | Python · Playwright |
| Phase 2 | スプレッドシート転記 | Google Sheets API |
| Phase 3 | Premiere Pro自動化 | osascript · ExtendScript |
| Phase 4 | ホッシーくんUI | React · CSS Sprites |
| Phase 5 | 音声インターフェース | Porcupine · Whisper |
| Phase 6 | リモートアクセス | Cloudflare Tunnel |
| Phase 7+ | AI拡張（文字起こし・サムネ生成） | Claude API |

## 発表スライド

[https://hosshy-ads-slides.surge.sh](https://hosshy-ads-slides.surge.sh)

## プレゼンページ

[https://hosshy-ai-secretary.surge.sh](https://hosshy-ai-secretary.surge.sh)

## 進捗レポート

[https://hosshy-ads-progress.surge.sh](https://hosshy-ads-progress.surge.sh)

## ディレクトリ構成

```
.
├── README.md
├── docs/
│   └── requirements.md   # 要件定義書 ver.0.1
├── surge-deploy/
│   ├── index.html        # プレゼン用Webページ
│   └── hosshy.png        # ホッシーくんキャラクター素材
├── surge-deploy-progress/
│   └── index.html        # 開発進捗レポート
└── surge-deploy-slides/
    └── index.html        # 発表スライド
```

---

AIスクール卒業課題 · ver.0.1
