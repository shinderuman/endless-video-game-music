# Endless Video Game Music

macOSのMusic.appにあるローカル音源をブラウザで再生し、PyMusicLooperが検出した
ループ候補をスコア順に切り替えられるローカルプレイヤーです。音源は外部へ送信せず、
Pythonサーバーから同じMacのChromeへ配信します。

## 動作環境

- macOSとMusic.app
- Python 3.12以上
- [uv](https://docs.astral.sh/uv/)
- FFmpeg（`ffmpeg`と`ffprobe`）
- Chrome

Music.app上に表示されていても、Apple Musicのストリーミングのみでローカルファイルが
存在しない曲は再生対象になりません。DockerはMusic.appの自動操作とホスト音源への
アクセスを複雑にするため使用しません。

## セットアップと起動

```sh
brew install uv ffmpeg
make setup
make open
```

`make open`は既定で `http://127.0.0.1:8765/` を開きます。ブラウザを自動で開かず
サーバーだけ起動する場合は次を使います。

```sh
make run
```

ポートを変更する場合:

```sh
make run PORT=9000
```

初回起動時はMusic.appからプレイリストを自動取得します。macOSから確認された場合は、
サーバーを起動したターミナルによるMusic.appの操作を許可してください。拒否した場合も
画面右上の「Musicを再読込」から再試行できます。

## 主な機能

- Music.appのプレイリストとアルバムを自動読込
- 曲名・アーティスト・アルバム検索
- 通常再生とPyMusicLooperによるループ再生
- ループ候補をスコアの高い順に切替
- 前の曲、次の曲、ランダム再生
- 指定した分数ごとに4秒フェードして次の曲へ移動
- 次の曲をバックグラウンド解析
- 埋め込み画像またはMusic.appからジャケット画像を表示
- 解析結果・ライブラリ・ジャケット画像をユーザー別にキャッシュ

キャッシュは `~/Library/Caches/Endless Video Game Music/` に保存します。Music Bridgeの
既存キャッシュがある場合だけ初回読込の高速化に利用しますが、Music Bridgeの導入は
必要ありません。

## 開発用コマンド

```sh
make doctor  # 外部依存を確認
make test    # pytest
make lint    # ruff
make format  # ruff format
make check   # lintとテスト
```
