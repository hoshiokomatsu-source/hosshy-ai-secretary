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

## プレゼンページ

[https://hosshy-ai-secretary.surge.sh](https://hosshy-ai-secretary.surge.sh)

## 進捗レポート

[https://hosshy-progress.surge.sh](https://hosshy-progress.surge.sh)

## ディレクトリ構成

```
.
├── README.md
├── docs/
│   └── requirements.md   # 要件定義書 ver.0.1
└── surge-deploy/
    ├── index.html        # プレゼン用Webページ
    └── hosshy.png        # ホッシーくんキャラクター素材
└── surge-deploy-progress/
    └── index.html        # 開発進捗レポート
```

---

AIスクール卒業課題 · ver.0.1
