# Endless Video Game Music

ゲーム音楽CDから取り込んだローカル音源を、事前生成したループ定義に従ってMacとAndroidのブラウザで無限ループ再生する個人用プロジェクトです。

- プロジェクト表示名: `Endless Video Game Music`
- GitHubリポジトリ名: `endless-video-game-music`
- 製品CLIコマンド名: `vgm`
- 現在の状態: **要件・設計確定済み、PoC未実施、製品実装禁止**

## 最終的に作るもの

1. **定義JSON出力CLI**
   - M3U8プレイリスト内の曲だけを対象にする
   - PyMusicLooperでループ候補を解析する
   - 採用基準を満たした曲だけを定義JSONへ出力する
   - 音源タグを使ってアルバム・曲・ディスク・トラック情報を構成する
   - 製品コマンドは `vgm generate`

2. **静的HTMLプレイヤー**
   - macOSとAndroidのChrome・Edgeに対応する
   - ローカル音源を端末内で再生し、音源をアップロードしない
   - 定義JSONに存在するアルバムと曲だけを検索・表示する
   - PyMusicLooperが検出した任意のループ構造を再生する
   - 初期公開先はGitHub Pagesを候補とする

## 最初に読む順序

1. [`CODEX_START.md`](CODEX_START.md)
2. [`AGENTS.md`](AGENTS.md)
3. [`DESIGN.md`](DESIGN.md)
4. [`POC.md`](POC.md)
5. [`POC_RESULTS.md`](POC_RESULTS.md)

承認済みUI試作は [`references/approved-player-mockup.html`](references/approved-player-mockup.html) です。これは製品コードではなく、外観と操作仕様の正本となる参照資料です。

M3U8の参考入力は [`references/sample-playlist.m3u8`](references/sample-playlist.m3u8) です。製品解析では利用者が指定する完全版M3U8を使います。

## 重要な停止条件

PoCがすべて完了し、利用者が明示的に総合GOを出すまで製品実装へ進んではいけません。各PoC段階の完了後にも一度停止し、結果を報告して次段階の明示的な許可を待ちます。

## 外部調査対象

- PyMusicLooper
  - https://github.com/arkrow/PyMusicLooper
  - https://github.com/arkrow/PyMusicLooper/blob/master/CLI_README.md
- 利用者の既存プロジェクト
  - ローカル: `~/src/music-bridge`
  - https://github.com/shinderuman/music-bridge
  - Android対応コミット: `0f12fa6b3c8351e7e4a54fbbb11c14ea5af86711`

外部資料の記載だけを信用せず、インストール済みバージョンのヘルプ確認と実音源・実エミュレーターを使った動作確認を行います。
