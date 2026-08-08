# Endless Video Game Music

macOSのMusic.appにあるローカルライブラリを直接読み込み、ゲーム音楽向けに
ループ位置を自動検出・波形補正して連続再生するローカルWebプレイヤーです。
Music.appのプレイリストやアルバムを、そのままChromeから選んで再生できます。

## 動作環境

- macOSとMusic.app
- [Local Web App Server](../local-web-app-server)
- Python 3.12以上
- [uv](https://docs.astral.sh/uv/)
- FFmpeg（`ffmpeg`と`ffprobe`）
- Chrome

Music.appに登録されたローカル音源ファイルを再生します。

## セットアップと起動

```sh
brew install uv ffmpeg
make setup
make library
make install
```

`make install` はアプリを Local Web App Server にインストールし、ホストを再起動して
`http://127.0.0.1:8766/apps/endless-vgm/` を開きます。アプリ一覧は
`http://127.0.0.1:8766/` です。

インストール済みアプリとホストを再起動する場合:

```sh
make run
```

ブラウザだけを開く場合:

```sh
make open
```

`make library`はMusic.appの全ライブラリと全プレイリストをキャッシュへ一括取得します。
曲数によっては数十分かかります。macOSから確認された場合は、ターミナルによる
Music.appの操作を許可してください。Music.appの内容を更新したときも同じコマンドを
実行します。通常起動では完成済みキャッシュを読み込むため、この処理を行いません。
ターミナルには進捗率とETAを同じ行で表示します。進捗と実行結果は
`~/Library/Caches/Endless Video Game Music/library-refresh.log`にも保存されます。

## 主な機能

- Music.appの全ライブラリとプレイリストを直接読み込み、そのまま再生
- PyMusicLooperの最上位候補を波形で再検証し、「標準」「位置調整」
  「つなぎ目優先」の3方式から選択
- 曲の先頭を一度再生した後、検出した終端からループ始点へサンプル精度で戻る連続再生
- PyMusicLooperのスコア上位20件も補助候補として選択
- 解析結果を曲ごとに保存し、次の曲を再生中に解析してプレイリスト再生を継続

キャッシュは `~/Library/Caches/Endless Video Game Music/` に保存します。Music Bridgeの
既存キャッシュがある場合は初回読込の高速化に利用します。

## 開発用コマンド

```sh
make doctor  # 外部依存を確認
make library # Music.appライブラリを更新
make install # Local Web App Serverへインストールして起動
make run     # Local Web App Serverを再起動
make stop    # Local Web App Serverを停止
make test    # pytest
make lint    # ruff
make format  # ruff format
make check   # lintとテスト
```
