# Stage 0 command log

- 実施日時: 2026-07-28 13:03–13:13 JST
- 作業ディレクトリ: `/Users/shinderumanm/src/endless-video-game-music`
- 記録形式: コマンド、終了コード、標準出力・標準エラー
- 注記: `system_profiler`の生出力に含まれるシリアル番号、Hardware UUID、Provisioning UDIDは保存せず、必要な非機密項目だけを再取得した。
- 後続仕様変更: 2026-07-28にEdgeは互換動作の期待対象だが必須検証対象外となった。以下のEdge調査記録はStage 0実施時の履歴として保持する。

## macOS、CPU、ディスク

### `sw_vers`

- 終了コード: `0`
- 標準出力:

```text
ProductName:		macOS
ProductVersion:		26.5.2
BuildVersion:		25F84
```

### `uname -m`

- 終了コード: `0`
- 標準出力:

```text
arm64
```

### `system_profiler SPHardwareDataType | rg 'Model Name:|Model Identifier:|Chip:|Total Number of Cores:|Memory:'`

- 終了コード: `0`
- 標準出力:

```text
      Model Name: Mac mini
      Model Identifier: Macmini9,1
      Chip: Apple M1
      Total Number of Cores: 8 (4 Performance and 4 Efficiency)
      Memory: 16 GB
```

- 標準エラー:

```text
Error fetching hw.cpufamily: -1
```

### `df -h / /Users/shinderumanm/src/endless-video-game-music /Volumes/CodexVault '/Volumes/2TB HDD'`

- 終了コード: `0`
- 標準出力:

```text
Filesystem        Size    Used   Avail Capacity iused ifree %iused  Mounted on
/dev/disk3s1s1   228Gi    12Gi   115Gi    10%    459k  1.2G    0%   /
/dev/disk3s5     228Gi    90Gi   115Gi    44%    1.5M  1.2G    0%   /System/Volumes/Data
/dev/disk9s1     223Gi   2.0Gi   221Gi     1%     138  2.3G    0%   /Volumes/CodexVault
/dev/disk5s2     1.8Ti   1.1Ti   707Gi    63%     31k  7.4G    0%   /Volumes/2TB HDD
```

## Python、uv、PyMusicLooper

### `python3 --version`

- 終了コード: `0`
- 標準出力:

```text
Python 3.14.6
```

### `uv --version`（導入前）

- 終了コード: `127`
- 標準エラー:

```text
zsh:1: command not found: uv
```

### `brew install uv openjdk@21`

- 終了コード: `0`
- 結果:
  - `uv 0.11.32`を`/opt/homebrew/Cellar/uv/0.11.32`へ導入
  - `openjdk@21 21.0.12`を`/opt/homebrew/Cellar/openjdk@21/21.0.12`へ導入
  - `openjdk@21`はkeg-onlyで、システムJavaとしてはリンクしていない

### `uv --version`（導入後）

- 終了コード: `0`
- 標準出力:

```text
uv 0.11.32 (Homebrew 2026-07-23 aarch64-apple-darwin)
```

### `/opt/homebrew/opt/openjdk@21/bin/java -version`

- 終了コード: `0`
- 標準エラー:

```text
openjdk version "21.0.12" 2026-07-21
OpenJDK Runtime Environment Homebrew (build 21.0.12)
OpenJDK 64-Bit Server VM Homebrew (build 21.0.12, mixed mode, sharing)
```

### `pipx list`

- サンドボックス内終了コード: `1`
- サンドボックス内標準エラーの要点:

```text
PermissionError: [Errno 1] Operation not permitted:
'/Users/shinderumanm/Library/Logs/pipx/cmd_2026-07-28_13.04.57.log'
```

- 権限昇格後終了コード: `0`
- 権限昇格後標準出力:

```text
venvs are in /Users/shinderumanm/Library/Application Support/pipx/venvs
apps are exposed on your $PATH at /Users/shinderumanm/.local/bin
manual pages are exposed at /Users/shinderumanm/.local/share/man
shell completions are exposed at /Users/shinderumanm/.local/share
   package pymusiclooper 3.6.0, installed using Python 3.14.6
    - pymusiclooper
```

### `pymusiclooper --version`

- サンドボックス内終了コード: `1`
- サンドボックス内標準エラー:

```text
RuntimeError: cannot cache function '_find_candidate_pairs': no locator available
for file '/Users/shinderumanm/Library/Application Support/pipx/venvs/pymusiclooper/lib/python3.14/site-packages/pymusiclooper/analysis.py'
```

- 権限昇格後終了コード: `0`
- 権限昇格後標準出力:

```text
pymusiclooper 3.6.0
```

### `pymusiclooper --help`（権限昇格）

- 終了コード: `0`
- 標準出力:

```text
Usage: pymusiclooper [OPTIONS] COMMAND [ARGS]...

A program for repeating music seamlessly and endlessly, by automatically
finding the best loop points.

Options:
  --debug        -d  Enables debugging mode.
  --verbose      -v  Enables verbose logging output.
  --interactive  -i  Enables interactive mode to manually preview/choose the
                     desired loop point.
  --samples      -s  Display all the loop points shown in interactive mode in
                     sample points instead of the default mm:ss.sss format.
  --version          Show the version and exit.
  --help             Show this message and exit.

Play Commands:
  play         Play an audio file on repeat from the terminal with the best
               discovered loop points, or a chosen point if interactive mode
               is active.
  play-tagged  Skips loop analysis and reads the loop points directly from the
               tags present in the file.

Export Commands:
  export-points  Export the best discovered or chosen loop points to a text
                 file or to the terminal.
  split-audio    Split the input audio into intro, loop and outro sections.
  tag            Adds metadata tags of loop points to a copy of the input
                 audio file(s).
  extend         Create an extended version of the input audio by looping it
                 to a specific length.

Full documentation and examples can be found at
https://github.com/arkrow/PyMusicLooper
```

### `pymusiclooper export-points --help`（権限昇格）

- 終了コード: `0`
- 標準出力:

```text
Usage: pymusiclooper export-points [OPTIONS]

Export the best discovered or chosen loop points to a text file or to the
terminal.

Basic options:
  --path PATH
      Path to the audio file(s). Mutually exclusive with --url; at least one
      is required.
  --url URL
      Link to a stream supported by yt-dlp. Mutually exclusive with --path;
      at least one is required.
  --export-to [stdout|txt]
      STDOUT prints loop points; TXT appends to loop.txt. Default: STDOUT.
  --alt-export-top INTEGER
      Export the top N loop points. -1 exports all points.
  --fmt [samples|seconds|time]
      Default: samples.

Advanced loop options:
  --min-duration-multiplier FLOAT RANGE [0.0<x<1.0]  Default: 0.35.
  --min-loop-duration FLOAT RANGE [x>0]
  --max-loop-duration FLOAT RANGE [x>0]
  --approx-loop-position FLOAT RANGE... [x>=0]
  --brute-force
  --disable-pruning

Export options:
  --output-dir -o DIRECTORY

Batch options:
  --recursive -r
  --flatten -f

Options:
  --help
```

### `pymusiclooper export-points /definitely/not/a/real/audio-file.m4a`

- 終了コード: `2`
- 標準エラー:

```text
Usage: pymusiclooper export-points [OPTIONS]
Try 'pymusiclooper export-points --help' for help
Error: Missing one of the required mutually exclusive options from
'audio path' option group:
  '--path'
  '--url'
```

### `pymusiclooper export-points --path /definitely/not/a/real/audio-file.m4a`

- 終了コード: `2`
- 標準エラー:

```text
Usage: pymusiclooper export-points [OPTIONS]
Try 'pymusiclooper export-points --help' for help
Error: Invalid value for '--path': Path
'/definitely/not/a/real/audio-file.m4a' does not exist.
```

PyMusicLooperの実音源解析は`POC.md`でStage 0の対象外とされているため実行していない。

## ffmpeg、ffprobe

### `ffmpeg -version`

- 終了コード: `0`
- 標準出力:

```text
ffmpeg version 8.1.2 Copyright (c) 2000-2026 the FFmpeg developers
built with Apple clang version 21.0.0 (clang-2100.0.123.102)
configuration: --prefix=/opt/homebrew/Cellar/ffmpeg/8.1.2_1 --enable-shared --enable-pthreads --enable-version3 --cc=clang --host-cflags= --host-ldflags= --enable-ffplay --enable-gpl --enable-libsvtav1 --enable-libopus --enable-libx264 --enable-libmp3lame --enable-libdav1d --enable-libvmaf --enable-libvpx --enable-libx265 --enable-openssl --enable-videotoolbox --enable-audiotoolbox --enable-neon
libavutil      60. 26.102 / 60. 26.102
libavcodec     62. 28.102 / 62. 28.102
libavformat    62. 12.102 / 62. 12.102
libavdevice    62.  3.102 / 62.  3.102
libavfilter    11. 14.102 / 11. 14.102
libswscale      9.  5.102 /  9.  5.102
libswresample   6.  3.102 /  6.  3.102

Exiting with exit code 0
```

### `ffprobe -version`

- 終了コード: `0`
- 標準出力:

```text
ffprobe version 8.1.2 Copyright (c) 2007-2026 the FFmpeg developers
built with Apple clang version 21.0.0 (clang-2100.0.123.102)
configuration: --prefix=/opt/homebrew/Cellar/ffmpeg/8.1.2_1 --enable-shared --enable-pthreads --enable-version3 --cc=clang --host-cflags= --host-ldflags= --enable-ffplay --enable-gpl --enable-libsvtav1 --enable-libopus --enable-libx264 --enable-libmp3lame --enable-libdav1d --enable-libvmaf --enable-libvpx --enable-libx265 --enable-openssl --enable-videotoolbox --enable-audiotoolbox --enable-neon
libavutil      60. 26.102 / 60. 26.102
libavcodec     62. 28.102 / 62. 28.102
libavformat    62. 12.102 / 62. 12.102
libavdevice    62.  3.102 / 62.  3.102
libavfilter    11. 14.102 / 11. 14.102
libswscale      9.  5.102 /  9.  5.102
libswresample   6.  3.102 /  6.  3.102
```

### 実M4Aの`ffprobe`

コマンド:

```text
ffprobe -v error -show_entries format=format_name,duration \
  -show_entries stream=codec_name,sample_rate,channels -of json \
  '/Volumes/2TB HDD/Music/Music/Compilations/DRAG-ON DRAGOON Original Soundtrack [Disc 1]/1-01 ミッション選択.m4a'
```

- 終了コード: `0`
- 標準出力:

```json
{
    "programs": [],
    "stream_groups": [],
    "streams": [
        {
            "codec_name": "aac",
            "sample_rate": "44100",
            "channels": 2
        }
    ],
    "format": {
        "format_name": "mov,mp4,m4a,3gp,3g2,mj2",
        "duration": "24.984671"
    }
}
```

### 実M4Aの先頭1秒デコード

コマンド:

```text
ffmpeg -v error -i \
  '/Volumes/2TB HDD/Music/Music/Compilations/DRAG-ON DRAGOON Original Soundtrack [Disc 1]/1-01 ミッション選択.m4a' \
  -t 1 -f null -
```

- 終了コード: `0`
- 標準出力: なし
- 標準エラー: なし

### 存在しないファイルの`ffprobe`

コマンド:

```text
ffprobe -v error -show_format /definitely/not/a/real/audio-file.m4a
```

- 終了コード: `1`
- 標準エラー:

```text
/definitely/not/a/real/audio-file.m4a: No such file or directory
```

## Android SDK、ADB、AVD、ブラウザ

### `adb version`

- 終了コード: `0`
- 標準出力:

```text
Android Debug Bridge version 1.0.41
Version 37.0.1-15733141
Installed as /opt/homebrew/bin/adb
Running on Darwin 25.5.0 (arm64)
```

### `/Users/shinderumanm/Library/Android/sdk/emulator/emulator -version`

- サンドボックス内終了コード: `134`
- サンドボックス内標準エラー:

```text
Incompatible processor. This Qt build requires the following features:
    neon
```

- 権限昇格後終了コード: `0`
- 権限昇格後標準出力の先頭:

```text
Android emulator version 36.6.11.0 (build_id 15507667) (CL:N/A)
```

### `/Users/shinderumanm/Library/Android/sdk/emulator/emulator -list-avds`

- 終了コード: `0`
- 標準出力:

```text
music_bridge_api35
```

### `sdkmanager`と`avdmanager`（JDK導入前）

- `sdkmanager --list_installed`: 終了コード`1`
- `avdmanager list avd`: 終了コード`1`
- 共通標準エラー:

```text
The operation couldn’t be completed. Unable to locate a Java Runtime.
```

### `JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home sdkmanager --version`

- 終了コード: `0`
- 標準出力:

```text
20.0
```

### 既存SDKルートの`--list_installed`

コマンド:

```text
JAVA_HOME=/opt/homebrew/opt/openjdk@21/libexec/openjdk.jdk/Contents/Home \
sdkmanager --sdk_root=/Users/shinderumanm/Library/Android/sdk --list_installed
```

- 終了コード: `0`
- 標準出力:

```text
Installed packages:
  Path                                           | Version | Description
  emulator                                       | 36.6.11 | Android Emulator
  platform-tools                                 | 37.0.0  | Android SDK Platform-Tools
  platforms;android-35                           | 2       | Android SDK Platform 35
  system-images;android-35;google_apis;arm64-v8a | 9       | Google APIs ARM 64 v8a System Image
```

### 既存SDKルートの`avdmanager list avd`

- 終了コード: `0`
- 標準出力:

```text
Available Android Virtual Devices:

The following Android Virtual Devices could not be loaded:
    Name: music_bridge_api35
    Path: /Users/shinderumanm/.android/avd/music_bridge_api35.avd
   Error: Missing system image for Google APIs arm64-v8a music bridge api35.
```

`avdmanager`は不整合を報告するが、同AVDは`emulator -list-avds`に現れ、実際の起動・Androidテストは成功した。

### 既存AVDの起動とブラウザ確認

起動コマンド:

```text
/Users/shinderumanm/Library/Android/sdk/emulator/emulator \
  @music_bridge_api35 -no-window -no-audio -no-snapshot-save -no-metrics
```

- 終了コード: `0`
- 機械確認結果:

```text
emulator appeared: emulator-5554
emulator boot completed
Android release: 15
API level: 35
ABI: arm64-v8a
package:com.google.android.webview
package:com.android.chrome
PACKAGE com.android.chrome
    versionCode=636771932 minSdk=29 targetSdk=34
    versionName=124.0.6367.219
    versionCode=636771932 minSdk=26 targetSdk=34
    versionName=124.0.6367.219
PACKAGE com.microsoft.emmx
```

`com.microsoft.emmx`には`versionName`がなく、Android Edgeは未導入。確認後に`adb emu kill`でAVDを停止した。

### macOSブラウザ

`plutil -p '/Applications/Google Chrome.app/Contents/Info.plist'`:

- 終了コード: `0`
- 確認結果:

```text
"CFBundleShortVersionString" => "150.0.7871.187"
"CFBundleVersion" => "7871.187"
```

`test -d '/Applications/Microsoft Edge.app'`:

- 終了コード: `1`
- 標準出力・標準エラー: なし

macOS EdgeのHomebrew Cask導入は、Stage 0調査の権限範囲を超えるシステム変更として実行環境の承認レビューで拒否されたため、迂回せず未導入として記録した。

## M3U8参考入力と承認済みモックアップ

Node.jsで全行を読み、`#EXTINF`と絶対パスの組、ファイル存在、拡張子、モックアップ内データとの順序・パス・秒数一致を検証した。

- 終了コード: `0`
- 標準出力:

```json
{
  "lineCount": 729,
  "trackCount": 364,
  "extinfCount": 364,
  "absolutePathCount": 364,
  "m4aCount": 364,
  "existingPathCount": 364,
  "missingPathCount": 0,
  "mockupTrackCount": 364,
  "mockupPathDurationMismatchCount": 0,
  "uniqueAlbumDirectoryCount": 19,
  "nfcDifferentPathCount": 78
}
```

## `music-bridge`

### Git状態

`git -C /Users/shinderumanm/src/music-bridge status --short --branch`:

- 終了コード: `0`
- 標準出力:

```text
## main
```

`git -C /Users/shinderumanm/src/music-bridge rev-parse HEAD`:

- 終了コード: `0`
- 標準出力:

```text
b2e105a46e73be7a988f72f22a5f67d31b4eac44
```

`git -C /Users/shinderumanm/src/music-bridge show -s --format=fuller 0f12fa6b3c8351e7e4a54fbbb11c14ea5af86711`:

- 終了コード: `0`
- 対象コミット:

```text
0f12fa6b3c8351e7e4a54fbbb11c14ea5af86711
feat: add direct Android synchronization
```

`git branch --contains`では`main`と`codex/refactor-architecture`が対象コミットを含む。

### 関連単体テスト

`go version`:

```text
go version go1.26.5 darwin/arm64
```

`go test -count=1 ./internal/portable ./internal/layout`:

- サンドボックス内終了コード: `1`
- 原因: `~/Library/Caches/go-build`への書き込みが拒否された
- 権限昇格後終了コード: `0`
- 標準出力:

```text
ok  	music-bridge/internal/portable	0.741s
ok  	music-bridge/internal/layout	0.405s
```

### 全テストとAVD自動起動・停止

`make test`:

- 終了コード: `0`
- 標準出力:

```text
./tools/test.sh
?   	music-bridge/cmd/music-bridge	[no test files]
ok  	music-bridge/internal/android	44.722s
ok  	music-bridge/internal/app	2.573s
ok  	music-bridge/internal/diagnostic	1.202s
ok  	music-bridge/internal/drive	1.084s
ok  	music-bridge/internal/layout	2.739s
ok  	music-bridge/internal/library	1.497s
ok  	music-bridge/internal/musicapp	22.519s
ok  	music-bridge/internal/notify	2.220s
ok  	music-bridge/internal/playlistfile	2.020s
ok  	music-bridge/internal/playlistselect	2.233s
ok  	music-bridge/internal/portable	2.087s
ok  	music-bridge/internal/targetlock	1.709s
ok  	music-bridge/internal/textfmt	1.684s
ok  	music-bridge/internal/tui	1.877s
```

テスト後の`adb devices -l`:

- 終了コード: `0`
- 標準出力:

```text
List of devices attached
```

AVDは自動停止済み。

## `music-bridge`既存資産の機械確認

- `internal/portable/path.go`
  - `Key`: Android側の私用領域文字を論理文字へ戻し、NFC化、小文字化
  - `MutationCandidates`: NFC、元表現、NFDの順に重複なしで候補化
  - `AndroidVisible` / `LogicalFromAndroid`: FAT/exFATの予約文字、制御文字、末尾空白・末尾ピリオドをU+F000台へ可逆変換
  - `IsAppleDouble`: `._`ファイルを除外
- `internal/layout/layout.go`
  - 共通ルート: `music-bridge`
  - ライブラリ: `Library`
  - manifest: `.music-bridge-manifest.json`
  - pending manifest: `.music-bridge-pending-manifest`
  - target marker、library marker、partial、lockの共通名を定義
- `internal/playlistfile/playlist.go`
  - UTF-8 BOM付き`#EXTM3U`
  - `music-bridge`配下からの相対論理パス
  - Android可視名へ変換して出力
- `tools/test.sh`
  - 起動済みAVDを再利用
  - なければ`music_bridge_api35`をヘッドレス起動
  - ADB出現と`sys.boot_completed=1`を待機
  - `go test -count=1 ./...`後に自動停止
- `.android-e2e/source`
  - Stage 0確認時は空
  - エミュレーターテストデータは`testing.T.TempDir`とAndroid側一時ディレクトリへテスト実行時に生成し、終了時に削除
