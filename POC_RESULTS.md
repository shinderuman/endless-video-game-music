# POC_RESULTS.md — PoC結果記入先

この文書はCodexが各Stageの実行後に更新します。結果が未実施の段階を推測で埋めてはいけません。

## 総合状態

- 現在のStage: Stage 1
- 製品実装: 禁止
- 総合判定: **NO-GO（旧要件）**
- 利用者の総合GO: なし

## Stage 0: 実行環境・既存資産調査

### 実施日時

2026-07-28 13:03–13:13 JST

### 環境

| 項目 | 結果 |
|---|---|
| macOS | 26.5.2（Build 25F84） |
| CPU | Apple M1、arm64、8コア、メモリ16 GB |
| 空き容量 | システムデータ115 GiB、`CodexVault` 221 GiB、`2TB HDD` 707 GiB |
| Python | 3.14.6 |
| uv | 0.11.32。Stage 0中にHomebrewで導入 |
| PyMusicLooper | 3.6.0、pipx、Python 3.14.6。権限昇格時にCLI起動成功 |
| ffmpeg | 8.1.2 |
| ffprobe | 8.1.2 |
| ADB | 1.0.41、Platform Tools 37.0.1-15733141 |
| Android SDK | Platform 35 rev.2、Command-line Tools 20.0、Platform Tools 37.0.0、Emulator 36.6.11、Google APIs arm64-v8a system image rev.9 |
| AVD | `music_bridge_api35`、Android 15 / API 35 / arm64-v8a。ヘッドレス起動成功 |
| Emulator Chrome | 124.0.6367.219、起動したAVD上で確認 |
| Emulator Edge（参考、検証対象外） | 未導入。`com.microsoft.emmx`なし |
| macOS Chrome | 150.0.7871.187 |
| macOS Edge（参考、検証対象外） | 未導入 |
| `~/src/music-bridge` | 存在。`main`、HEAD `b2e105a46e73be7a988f72f22a5f67d31b4eac44`、作業ツリーclean |

### 実行コマンド

コマンド、標準出力・標準エラー、終了コードは
[`poc/stage0/COMMAND_LOG.md`](poc/stage0/COMMAND_LOG.md)へ保存した。

主なコマンド:

- `sw_vers`
- `uname -m`
- `system_profiler SPHardwareDataType`
- `df -h`
- `python3 --version`
- `uv --version`
- `pipx list`
- `pymusiclooper --version`
- `pymusiclooper --help`
- `pymusiclooper export-points --help`
- `ffmpeg -version`
- `ffprobe -version`
- 実M4Aの`ffprobe`と先頭1秒の`ffmpeg`デコード
- `adb version`
- `adb devices -l`
- `emulator -version`
- `emulator -list-avds`
- `sdkmanager --list_installed`
- `avdmanager list avd`
- 既存AVDのヘッドレス起動、Androidプロパティ・インストール済みブラウザ確認、停止
- `git -C ~/src/music-bridge status --short --branch`
- `git -C ~/src/music-bridge rev-parse HEAD`
- `git -C ~/src/music-bridge show 0f12fa6b3c8351e7e4a54fbbb11c14ea5af86711`
- `go test -count=1 ./internal/portable ./internal/layout`
- `make test`

### 既存資産

- `references/sample-playlist.m3u8`
  - 729行、364曲、364個の`#EXTINF`、364個の絶対パス
  - 全364音源が`/Volumes/2TB HDD`上に存在
  - 全曲M4A、19アルバムディレクトリ
  - 78パスはNFC表現と異なり、Unicode正規化差の実データを含む
  - 承認済みモックアップ内364曲と、順序・パス・秒数が全件一致
- `~/src/music-bridge`
  - 対象コミット`0f12fa6b3c8351e7e4a54fbbb11c14ea5af86711`が存在し、現在の`main`に含まれる
  - `internal/portable`
    - NFC/NFD・大文字小文字を吸収する論理キー
    - FAT/exFATの予約文字、制御文字、末尾空白・末尾ピリオドとAndroid表示名の可逆変換
    - AppleDouble除外
  - `internal/layout`
    - ドライブ・Android共通の`music-bridge/Library`構成
    - `.music-bridge-manifest.json`、pending manifest、marker、partial、lock
  - `internal/playlistfile`
    - UTF-8 BOM付きM3U
    - `music-bridge`配下の相対論理パス
    - Android可視名での出力
  - Android Emulator統合テスト
    - 仮想ストレージへの転送、M3U・manifest、再開、再同期収束、ADB接続断を検証
    - `tools/test.sh`が`music_bridge_api35`を自動起動・待機・停止
  - `.android-e2e/source`は空。テストデータは実行時に一時生成・削除

### テスト

成功:

- `references/sample-playlist.m3u8`全364曲の構文・絶対パス・存在・M4A拡張子検証
- M3U8と承認済みモックアップの364曲について、順序・パス・秒数の全件一致
- 実M4Aを`ffprobe`でAAC / 44.1 kHz / stereoとして読取
- 実M4Aの先頭1秒を`ffmpeg`でエラーなしデコード
- PyMusicLooper 3.6.0のバージョン、全体ヘルプ、`export-points`ヘルプ
- PyMusicLooperのオプション不足・存在しないパスが終了コード`2`
- 既存AVDの起動、Android 15 / API 35 / arm64-v8a確認、停止
- `music-bridge`の`internal/portable`と`internal/layout`単体テスト
- `music-bridge`の`make test`全14テストパッケージ
- `make test`後にADB接続が0件で、AVDが停止済み

失敗・切り分け済み:

- サンドボックス内のPyMusicLooperは、pipx仮想環境内のNumbaキャッシュ作成が拒否され終了コード`1`
  - 同一コマンドは権限昇格で成功
- サンドボックス内のADB daemon起動とEmulator Qt起動は権限制約で失敗
  - 同一コマンドは権限昇格で成功
- JDK導入前の`sdkmanager`・`avdmanager`はJava Runtime不在で失敗
  - OpenJDK 21.0.12導入後、`sdkmanager`は成功
- `avdmanager list avd`は既存AVDのsystem image不在判定を表示
  - `emulator -list-avds`、実AVD起動、`music-bridge`全テストは成功するため、AVD資産自体は利用可能
- 存在しないM4Aの`ffprobe`は終了コード`1`

### 不足・障害

- `avdmanager`は既存AVDを不整合扱いする
  - 直接のEmulator CLIと`music-bridge`テストでは利用可能
  - Chrome検証に使う既存AVDの起動を妨げないため、現時点では非阻害事項
- PyMusicLooperはCodexサンドボックス内では起動できない
  - 権限昇格で正常起動するため、Stage 1は権限昇格して実施可能
- PyMusicLooper実音源解析はStage 0の対象外なので未実施
- 完全版約17,000曲M3U8はStage 0では未指定。Stage 1以降で必要

参考:

- 2026-07-28の利用者仕様変更により、必須検証対象はmacOS ChromeとAndroid Chromeのみ
- Edgeは互換動作を意図するが、導入・動作確認はPoCと製品受け入れの必須条件ではない

### 判定

- Codex判定: **GO**
  - Stage 1に必要な実音源、PyMusicLooper、ffmpeg、ffprobeを利用できる
  - 必須対象のmacOS ChromeとAndroid Chromeを利用できる
  - Stage 0の完了条件を満たす
- 利用者判定: **GO**（2026-07-28）
- 次Stage許可: **Stage 1開始許可あり**（2026-07-28）

---

## Stage 1: PyMusicLooper自動判定

### 開始許可

- 利用者許可: 2026-07-28
- 状態: 利用者判定待ち
- 機械解析・聴感ラベル集計: 完了
- 未完了:
  - 単一スコア閾値を採用するかの利用者判断

### 入力

- 完全版M3U8: リポジトリ内および既知のローカル配置には見つからなかった
- Music.appへのApple Events問い合わせ: macOSのAutomation権限で拒否（`-1743`）
- 暫定入力: Music Bridgeキャッシュ内の`GAME`プレイリスト
- キャッシュ全件: 17,569曲
- 音源パスあり: 17,547曲
- 音源パスなしの除外: 22曲
- 抽出した100曲の音源ファイル欠落: 0曲
- 既知非ループ対照群: Music Bridgeキャッシュ内の`東映マンガ祭り`プレイリスト
- 対照群の用途: 閾値評価だけ。製品のゲーム音楽解析対象には含めない

### 評価方法の変更

無作為100曲を50曲まで判定した時点で、利用者から「聴き慣れていない曲では
ループ境界の正解が曖昧になる」と指摘があった。このため、明示的な仕様変更として
次の標本を閾値評価の主標本にした。

- 利用者が聴き慣れた8作品から各5曲、合計40曲の既知ループ候補
- 全曲がボーカル曲でループ構造を持たないと利用者が判断した
  `東映マンガ祭り`から20曲の既知非ループ対照群
- シード`20260728`と設定ファイルにより抽出を再現可能にする

無作為100曲は解析安定性、処理時間、スコア分布を見る探索標本として保存し、
残り50曲の聴感判定は要求しない。

### 固定環境

- PyMusicLooperバージョン: 3.6.0
- ffprobeバージョン: 8.1.2
- コマンド: `pymusiclooper export-points`
- 固定オプション:
  - `--samples`
  - `--alt-export-top 1`
  - `--fmt samples`
  - `--export-to stdout`
- 実出力形式: `loop_start loop_end note_difference loudness_difference score`
- スコア生値の実範囲: 0〜1
- 当初文書の30、50、70領域は、生値では0.3、0.5、0.7に相当

### 無作為100曲の探索標本

- 乱数シード: `20260728`
- 抽出規則: `SHA-256(seed NUL originalIndex NUL sourcePath)`の昇順先頭100件
- 解析件数: 100
- 候補あり: 92
- 候補なし: 8
- 失敗: 0
- PyMusicLooper終了コード0: 100
- 候補スコア最小: 0.3548004104155839
- 候補スコア中央値: 0.9848415020567067
- 候補スコア最大: 0.9999786905035235
- 生成JSON:
  [`poc/stage1/artifacts/game-seed-20260728-n100/analysis.json`](poc/stage1/artifacts/game-seed-20260728-n100/analysis.json)
- 利用者レビュー一覧:
  [`poc/stage1/artifacts/game-seed-20260728-n100/review.csv`](poc/stage1/artifacts/game-seed-20260728-n100/review.csv)
- Chrome聴感レビュー画面:
  - `stage1-review`でlocalhost配信
  - 候補あり曲はWeb Audio APIで終了5秒前から開始位置へ連続ループ
  - 境界までの0.1秒単位カウントダウンと進捗バーを表示
  - 境界通過時にカードを点灯し、通過回数を表示
  - 候補なし曲は曲全体を再生可能
  - `loop`、`non_loop`、`loop_bad_points`の3ラベルと未判定への解除を
    `analysis.json`と`review.csv`へ即時保存
- Chrome検証スクリーンショット:
  [`poc/stage1/artifacts/game-seed-20260728-n100/review-chrome.png`](poc/stage1/artifacts/game-seed-20260728-n100/review-chrome.png)
- 曲別コマンド・標準出力・標準エラー・終了コード:
  [`poc/stage1/artifacts/game-seed-20260728-n100/logs`](poc/stage1/artifacts/game-seed-20260728-n100/logs)

ラベルなしの機械的な採用件数:

| 生値閾値 | 採用件数 |
|---:|---:|
| 0.3 | 92 |
| 0.5 | 91 |
| 0.7 | 90 |
| 0.8 | 84 |
| 0.9 | 71 |
| 0.95 | 59 |
| 0.99 | 44 |

これは正解率ではない。誤採用・誤除外は利用者ラベル受領後にのみ算出する。

利用者が確信を持って入力した50曲のラベルは、そのまま保存した。

| ラベル | 件数 |
|---|---:|
| `loop` | 38 |
| `non_loop` | 7 |
| `loop_bad_points` | 5 |
| 未判定 | 50 |

### 既知標本60曲

設定:
[`poc/stage1/evaluation-config.json`](poc/stage1/evaluation-config.json)

- 既知ループ候補: 8作品 × 5曲 = 40曲
- 既知非ループ対照群: `東映マンガ祭り`から20曲
- 抽出シード: `20260728`
- 解析件数: 60
- 候補あり: 54
- 候補なし: 6
- 失敗: 0
- 既知非ループ20曲: `non_loop`を初期ラベルとして設定
- 利用者ラベル: 60曲すべて入力済み
- 生成JSON:
  [`poc/stage1/artifacts/curated-seed-20260728-n60/analysis.json`](poc/stage1/artifacts/curated-seed-20260728-n60/analysis.json)
- 利用者レビュー一覧:
  [`poc/stage1/artifacts/curated-seed-20260728-n60/review.csv`](poc/stage1/artifacts/curated-seed-20260728-n60/review.csv)
- 抽出済み評価キャッシュ:
  [`poc/stage1/artifacts/curated-seed-20260728-n60/evaluation-cache.json`](poc/stage1/artifacts/curated-seed-20260728-n60/evaluation-cache.json)
- Chrome検証スクリーンショット:
  [`poc/stage1/artifacts/curated-seed-20260728-n60/review-chrome.png`](poc/stage1/artifacts/curated-seed-20260728-n60/review-chrome.png)
- 閾値評価JSON:
  [`poc/stage1/artifacts/curated-seed-20260728-n60/evaluation.json`](poc/stage1/artifacts/curated-seed-20260728-n60/evaluation.json)

| 評価群 | 候補あり | 候補なし | スコア最小 | 中央値 | 最大 |
|---|---:|---:|---:|---:|---:|
| ロマンシング サガ2 | 5 | 0 | 0.976292 | 0.997031 | 0.999490 |
| ロマンシング サガ3 | 4 | 1 | 0.984482 | 0.998311 | 0.999884 |
| クロノ・トリガー | 3 | 2 | 0.529352 | 0.629056 | 0.998479 |
| ファイナルファンタジーIV | 5 | 0 | 0.834489 | 0.963764 | 0.995589 |
| ファイナルファンタジーV | 4 | 1 | 0.995336 | 0.998570 | 0.999369 |
| ファイナルファンタジーVI | 5 | 0 | 0.697172 | 0.864156 | 0.999272 |
| ファイナルファンタジーVII | 4 | 1 | 0.992375 | 0.999876 | 0.999894 |
| デビルサマナー ソウルハッカーズ | 4 | 1 | 0.929965 | 0.975265 | 0.980731 |
| 既知非ループ: 東映マンガ祭り | 20 | 0 | 0.761395 | 0.934978 | 0.984184 |

既知非ループ20曲すべてに候補が出ており、最低スコアも0.761395だった。
したがって、少なくともこの対照群では「高スコアならループ曲」という分離は
成立していない。

### 利用者ラベル反映後の集計

全60曲のラベル:

| ラベル | 件数 | 自動採用評価での扱い |
|---|---:|---|
| `loop` | 27 | 正しい採用対象 |
| `loop_bad_points` | 2 | 現在の候補点は採用不可 |
| `non_loop` | 31 | 採用対象外 |

自動採用は「候補あり、かつスコアが閾値以上」と定義した。`loop_bad_points`を
採用した場合は、ループ曲そのものを見つけた成功ではなく、現在の開始・終了点を
製品で使えない誤採用として数えた。

| スコア閾値 | 採用 | 正採用 | 誤採用 | 誤除外 | 適合率 | 再現率 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.30 | 54 | 27 | 27 | 0 | 50.0% | 100.0% |
| 0.50 | 54 | 27 | 27 | 0 | 50.0% | 100.0% |
| 0.70 | 51 | 27 | 24 | 0 | 52.9% | 100.0% |
| 0.80 | 49 | 27 | 22 | 0 | 55.1% | 100.0% |
| 0.90 | 42 | 25 | 17 | 2 | 59.5% | 92.6% |
| 0.95 | 34 | 24 | 10 | 3 | 70.6% | 88.9% |
| 0.99 | 20 | 19 | 1 | 8 | 95.0% | 70.4% |

観測した全スコア境界を総当たりした最小誤りは7件で、次の2点が同数だった。

| スコア閾値 | 誤採用 | 誤除外 | 適合率 | 再現率 |
|---:|---:|---:|---:|---:|
| 0.9637638639661321 | 4 | 3 | 85.7% | 88.9% |
| 0.9733497968714576 | 3 | 4 | 88.5% | 85.2% |

これは標本内で誤りが最小になる境界であり、採用閾値の提案ではない。
高スコアの非ループ曲と、それより低スコアの正常ループ曲が重なっているため、
単一スコア閾値では誤採用と誤除外を同時に解消できない。

### 曲末フェードアウト領域

利用者から、ゲームサントラはループ用音源の後ろにフェードアウトを付けることが多く、
ループ終了点が曲末の数秒にある場合は不正点とみなせる、という知見を受領した。
候補の「音源時間 − ループ終了時間」を曲末余白として集計した。

| 曲末余白の上限 | `loop` | `non_loop` | `loop_bad_points` |
|---:|---:|---:|---:|
| 3秒 | 0 | 0 | 0 |
| 5秒 | 0 | 0 | 1 |
| 10秒 | 4 | 1 | 1 |
| 15秒 | 10 | 4 | 2 |

- 5秒以内の除外は、正常ループを落とさず不正点1件を除外した
- もう1件の不正点は曲末余白11.004秒であり、5秒条件では検出できない
- 10秒へ広げても2件目を検出できず、正常ループ4件を誤除外する
- 15秒なら不正点2件を検出するが、正常ループ10件を誤除外する
- 既知非ループ20曲の誤採用を解決する条件ではない

したがって、曲末5秒の除外は補助的な安全条件として有望だが、2件中1件だけの
小標本であり、PyMusicLooperスコアの代替判定にはならない。

### 処理時間

- 100曲合計: 396.862秒
- 1曲中央値: 3.862秒
- 1曲最大: 8.654秒
- 17,000曲概算: 約18.24時間（単一プロセス、中央値による単純外挿）
- 既知標本60曲合計: 271.025秒
- 既知標本1曲中央値: 4.075秒
- 既知標本1曲最大: 18.967秒

### 判定

- Codex提案: **単一スコア閾値はNO-GO**
- 理由: 標本内でも最小7件の誤りが残り、非ループの高スコアと正常ループの
  低スコアが重なっている
- 曲末5秒条件: 将来の設計修正候補。単独採用を提案できる検証量ではない
- 利用者採用閾値: なし
- 利用者判定: **NO-GO**（2026-07-28）
- 利用者判断: 単一閾値による旧要件達成は困難。ローカル解析サーバーと
  WebUIによる候補選択方式へ要件を変更する

### 機械検証

- `ruff check`: 成功
- `ruff format --check`相当: 成功
- `pytest`: 30件成功
- 100曲の選択キー: 昇順、重複なし
- 初回と修正版の100音源パス・順序: 全件一致
- 100曲の音源ファイル存在: 全件成功
- 候補あり92件の開始・終了・スコア・サンプルレート欠落: 0件
- 候補なし8件の開始・終了・スコア誤設定: 0件
- 曲別ログ: 100件
- レビューCSV: ヘッダーを除き100件
- 完了済み成果物への同条件再実行:
  - 再解析ログ出力なし
  - 曲別ログ更新0件
  - `analysis.json`のSHA-256と更新時刻が不変
- Google Chrome 150.0.7871.187:
  - 無作為100曲と既知標本60曲の画面読込成功
  - 実M4AのAACデコード成功
  - Web Audio APIのループ再生開始成功
  - 5秒後の境界通過表示成功
  - 3種類のラベル保存・解除成功
  - 前後移動成功
  - JavaScriptコンソールエラー0件
- macOS Chromeで本番レビュー画面を開き、HTML・CSS・JavaScript・API・音源Range応答を確認
- 既知標本画面は初期状態で判定済み20/60と表示し、評価群名を表示
- 聴感ラベル:
  - `loop`: ループ対応
  - `non_loop`: ループ非対応
  - `loop_bad_points`: おそらくループ対応だが現在のループ点は不正
  - 未判定へ戻す操作も可能

実行コマンドと切り分けの詳細は
[`poc/stage1/COMMAND_LOG.md`](poc/stage1/COMMAND_LOG.md)に記録した。

---

## Stage 2: M3U8・タグ・複数ディスク統合

### M3U8

- 入力件数: 未確認
- 読取成功: 未確認
- 欠落パス: 未確認

### タグ取得

| 項目 | 成功件数 | 失敗件数 | 失敗例 |
|---|---:|---:|---|
| アルバム名 |  |  |  |
| 曲タイトル |  |  |  |
| ディスク番号 |  |  |  |
| トラック番号 |  |  |  |

### 複数ディスク統合規則案

未調査

### 実データ結果

未調査

### 判定

- Codex提案: 未判定
- 利用者GO: なし

---

## Stage 3: Mac・Android間の曲突合

### `music-bridge`調査

- HEAD: 未確認
- 対象コミット: 未確認
- `internal/portable`: 未確認
- manifest・M3U: 未確認
- Emulatorテスト: 未確認

### Codex B質問票

過去セッションを直接参照できない場合だけ、Codex Aがここへ質問を書きます。

未作成

### 比較結果

| 方式 | 対象件数 | 一致 | 未一致 | 重複 | 所要時間 | 実装量 |
|---|---:|---:|---:|---:|---:|---|
| music-bridge既存方式 |  |  |  |  |  |  |
| SHA-256 | 必要時のみ |  |  |  |  |  |

### 既知の難しい名前

未確認

### 判定

- Codex提案: 未判定
- 利用者採用方式: 未確定
- 利用者GO: なし

---

## Stage 4: HTMLプレイヤー実動作

### 環境別結果

| 環境 | フォルダ選択 | 突合 | MP3 | M4A | 複数ループ | 操作 | 検索性能 |
|---|---|---|---|---|---|---|---|
| macOS Chrome |  |  |  |  |  |  |  |
| Android Chrome |  |  |  |  |  |  |  |

Edgeは互換動作を意図するが、環境別結果の必須対象には含めない。

### 17,000曲相当の計測

- JSONサイズ: 未計測
- 読込時間: 未計測
- 初期表示時間: 未計測
- 検索応答時間: 未計測
- 最大描画件数: 未計測

### ネットワーク検査

- 音源アップロード: 未確認
- 不要なAPI通信: 未確認

### 判定

- Codex提案: 未判定
- 利用者GO: なし

---

## Stage 5: 中断・失敗・再実行

| シナリオ | 結果 | 証跡 |
|---|---|---|
| 中断後に完了曲を再解析しない | 未実施 |  |
| 追加曲だけ解析 | 未実施 |  |
| 1曲失敗後も継続 | 未実施 |  |
| 失敗曲だけ再試行 | 未実施 |  |
| 状態4区分 | 未実施 |  |
| 一部失敗で成功分更新 | 未実施 |  |
| 原子的置換 | 未実施 |  |
| 強制終了で既存JSON保護 | 未実施 |  |
| 終了コード識別 | 未実施 |  |
| ログ識別 | 未実施 |  |

### 判定

- Codex提案: 未判定
- 利用者GO: なし

---

## Stage 6: 総合判定

### 確定事項

未確定

### 残存未解決事項

未確認

### 設計変更案

未作成

### 総合判定

- Codex: 未判定
- 利用者: 未判定
- 製品実装許可: なし
