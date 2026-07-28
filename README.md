# Endless Video Game Music

macOSのMusic.appにあるローカル音源をブラウザで再生し、PyMusicLooperが検出した
ループ候補をスコア順に切り替えられるローカルプレイヤーです。同じMacで
Pythonサーバーを起動し、Chromeで操作します。

## 動作環境

- macOSとMusic.app
- Python 3.12以上
- [uv](https://docs.astral.sh/uv/)
- FFmpeg（`ffmpeg`と`ffprobe`）
- Chrome

Music.appに登録されたローカル音源ファイルを再生します。

## セットアップと起動

```sh
brew install uv ffmpeg
make setup
make open
```

`make open`は既定で `http://127.0.0.1:8765/` を開きます。サーバーを起動する場合は
次を使います。

```sh
make run
```

ポートを変更する場合:

```sh
make run PORT=9000
```

初回起動時はMusic.appからプレイリストを自動取得します。macOSから確認された場合は、
サーバーを起動したターミナルによるMusic.appの操作を許可してください。画面右上の
「Musicを再読込」からライブラリを更新できます。

## 主な機能

- Music.appの全ライブラリ、プレイリスト、アルバムを自動読込
- プレイリスト、アルバム、楽曲、プレイヤーの幅をドラッグ調整できる4ペイン表示
- 複数枚組アルバムをまとめ、Disc番号順と各Disc内の曲順で表示
- 曲名・アーティスト・アルバム検索
- 通常再生とPyMusicLooperによるループ再生
- 通常・ループ再生共通のシークバー、現在位置、曲の全長表示
- スコア上位20件のループ候補を前後移動または一覧から直接選択
- 前の曲、次の曲、ランダム再生
- 指定した分数ごとに4秒フェードして次の曲へ移動
- 次の曲をバックグラウンド解析
- 埋め込み画像またはMusic.appからジャケット画像を表示
- アプリの∞ロゴを使ったブラウザタブのファビコン
- 全操作のツールチップ表示
- 解析結果・ライブラリ・ジャケット画像をユーザー別にキャッシュ

キャッシュは `~/Library/Caches/Endless Video Game Music/` に保存します。Music Bridgeの
既存キャッシュがある場合は初回読込の高速化に利用します。

## 開発用コマンド

```sh
make doctor  # 外部依存を確認
make test    # pytest
make lint    # ruff
make format  # ruff format
make check   # lintとテスト
```
