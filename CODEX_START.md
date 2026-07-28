# CODEX_START.md

このファイルを最初の指示としてCodexまたは別のコーディングエージェントへ渡してください。

## 最初に必ず行うこと

1. 全設計文書を読む
2. 実行環境と外部依存を確認する
3. PoCを実行する
4. 結果を機械的に検証する
5. PoC結果を文書化する
6. GOまたはNO-GOを報告する
7. 製品実装へ進まず停止する

## 読む順序

1. `README.md`
2. `AGENTS.md`
3. `DESIGN.md`
4. `POC.md`
5. `POC_RESULTS.md`
6. `references/approved-player-mockup.html`
7. `references/sample-playlist.m3u8`

## 開始時の禁止事項

- 製品版の`vgm`を実装しない
- 製品版HTMLプレイヤーを実装しない
- 最終JSONスキーマを勝手に確定しない
- 曲突合方式を勝手に確定しない
- スコア閾値を勝手に確定しない
- 複数ディスク統合規則を勝手に確定しない
- 次のPoC段階へ勝手に進まない

## 最初の作業

`POC.md`の「Stage 0: 実行環境・既存資産調査」だけを実施してください。

Stage 0完了後、次を`POC_RESULTS.md`へ記入し、利用者へ報告して停止してください。

- OS、CPU、利用可能ディスク容量
- Python、uv、PyMusicLooper、ffmpeg、ffprobeの状態とバージョン
- `pymusiclooper`および`export-points`の実ヘルプ確認結果
- Android SDK、ADB、エミュレーター、Chromeの状態
- `~/src/music-bridge`の存在、Git状態、関連テスト、既存エミュレーター資産
- PoC実施を妨げる不足
- Stage 1へ進めるか

不足する依存を安全に導入できる場合は、自分で導入して再確認してください。利用者へコマンド実行を依頼しないでください。

Stage 0の報告後は、製品実装にもStage 1にも進まず停止してください。
