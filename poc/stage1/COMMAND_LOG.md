# Stage 1 command log

実施日: 2026-07-28 JST

## 入力調査

完全版M3U8はリポジトリ内および既知のローカル配置に見つからなかった。
Music.appへApple Eventsでプレイリスト取得を試みたが、macOSのAutomation権限により
`-1743`で拒否された。権限を迂回せず、既存のMusic Bridgeキャッシュを暫定入力にした。

入力:

```text
/Users/shinderumanm/Library/Caches/Music Bridge/library-cache.json
playlist: GAME
SHA-256: 51b006a680125b249991537c06dd106dada4e2ca8be49c8f02d9517b47891141
playlist tracks: 17569
tracks with source locations: 17547
tracks excluded for missing locations: 22
```

抽出規則:

```text
seed: 20260728
key: SHA-256(seed NUL originalIndex NUL sourcePath)
selection: key ascending, first 100
```

## PyMusicLooper実出力確認

バージョン:

```text
pymusiclooper 3.6.0
```

固定コマンド:

```text
pymusiclooper --samples export-points \
  --path SOURCE_FILE \
  --alt-export-top 1 \
  --fmt samples \
  --export-to stdout
```

候補ありの実出力例:

```text
3235817 6068152 0.01136796921491623 0.013481923689127484 0.9998070082182087
```

この出力から、スコア生値は百分率ではなく0〜1の値であることを確認した。

候補なしの実出力例:

```text
ERROR    No loop points found for "3-22 Batter Up.m4a" with current parameters.
```

候補なしでも終了コードは`0`で、メッセージは標準出力へ出る。端末幅により2行へ
折り返される場合もあるため、PoCは両方を`no_candidate`として扱う。

## スモーク実行

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-poc \
  -c '/Users/shinderumanm/Library/Caches/Music Bridge/library-cache.json' \
  -p GAME \
  -s 20260728 \
  -n 1 \
  -o /private/tmp/endless-vgm-stage1-smoke-top1
```

終了コード: `0`

結果:

```text
title: Back Street Of 九龍
loopStartSample: 3235817
loopEndSample: 6068152
scoreRaw: 0.9998070082182087
sampleRate: 44100
analysisDurationSeconds: 3.8546235829999205
analysisStatus: candidate
```

## 100曲実行

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-poc \
  -c '/Users/shinderumanm/Library/Caches/Music Bridge/library-cache.json' \
  -p GAME \
  -s 20260728 \
  -n 100 \
  -o poc/stage1/artifacts/game-seed-20260728-n100
```

有効な最終実行:

```text
start: 2026-07-28 20:57:04 JST
end: 2026-07-28 21:03:44 JST
process exit code: 0
candidate: 92
no_candidate: 8
failed: 0
```

曲ごとの実コマンド、標準出力、標準エラー、終了コード、解析時間は
`artifacts/game-seed-20260728-n100/logs/`の100個のJSONへ保存した。

## 静的検査とテスト

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 ruff format poc/stage1

UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 ruff check poc/stage1

UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 pytest -q poc/stage1/tests
```

最終結果:

```text
ruff format: 5 files left unchanged
ruff check: All checks passed!
pytest: 13 passed in 0.03s
```

後続のレビュー画面、評価標本ビルダー、既定ラベル・評価群対応を含む最終結果は
下記「既知標本60曲」の節に記録した。

## Chrome聴感レビュー

起動コマンド:

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-review \
  -a poc/stage1/artifacts/game-seed-20260728-n100/analysis.json \
  -p 8765
```

URL:

```text
http://127.0.0.1:8765/
```

レビュー画面は次を行う。

- 100曲の順次表示
- 実音源のHTTP Range配信
- 候補あり曲のWeb Audio APIによるAACデコード
- ループ終了5秒前から開始位置へ戻る連続ループ試聴
- 境界までのカウントダウンと進捗バー
- 境界通過時のカード点灯と通過回数表示
- 曲全体の再生
- `loop`、`non_loop`、`loop_bad_points`、未判定の保存
- 次の未判定曲への移動

自動検証は本番成果物のコピーを使い、ラベル保存後に解除した。本番の
`analysis.json`と`review.csv`へテストラベルは書き込んでいない。

```text
Google Chrome: 150.0.7871.187
page title: Stage 1 ループ聴感レビュー
tracks: 100
AAC decode and loop start: passed
visual boundary crossing after five seconds: passed
three labels and clear: passed
previous/next navigation: passed
JavaScript console errors: 0
```

スクリーンショット:

```text
artifacts/game-seed-20260728-n100/review-chrome.png
```

最終の静的検査・テスト:

```text
ruff format --check: 7 files already formatted
ruff check: All checks passed!
pytest: 22 passed in 0.04s
```

## 無作為標本の利用者ラベル

利用者が50曲を判定した時点で、聴き慣れていない曲ではループ境界の正解が
曖昧になると判明した。ラベルは次の状態で保存し、この100曲は探索標本へ変更した。

```text
loop: 38
non_loop: 7
loop_bad_points: 5
unlabeled: 50
```

## 既知標本60曲

利用者が指定した8作品から各5曲と、利用者が全曲を既知非ループと判断した
`東映マンガ祭り`プレイリストから20曲を、同じシードで再現可能に抽出した。

評価標本の生成:

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-build-evaluation \
  -c '/Users/shinderumanm/Library/Caches/Music Bridge/library-cache.json' \
  -f poc/stage1/evaluation-config.json \
  -o poc/stage1/artifacts/curated-seed-20260728-n60/evaluation-cache.json
```

終了コード: `0`

```text
output tracks: 60
known-loop candidates: 40
known non-loop controls: 20
evaluation-cache.json SHA-256:
3ee96d17bf8b7912b6ad8ad7db33dbe66044767dd35b85a3f50ed106bc102559
```

解析:

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-poc \
  -c poc/stage1/artifacts/curated-seed-20260728-n60/evaluation-cache.json \
  -p STAGE1_CURATED \
  -s 20260728 \
  -n 60 \
  -o poc/stage1/artifacts/curated-seed-20260728-n60
```

終了コード: `0`

```text
start: 2026-07-28 22:12:59 JST
end: 2026-07-28 22:18:01 JST
candidate: 54
no_candidate: 6
failed: 0
analysis duration total: 271.025 seconds
analysis duration median: 4.075 seconds
analysis duration max: 18.967 seconds
analysis.json SHA-256 before user labels:
bae2e9aead01c79d1bbd62328186dabf6a6245e7a739ec52d250b351ce69dfae
```

既知非ループ20曲はすべて候補ありで、スコアは
`0.7613948385772742`〜`0.984184040647604`、中央値は
`0.9349783973359898`だった。

Chrome検証:

```text
Google Chrome: 150.0.7871.187
tracks: 60
initial labeled count: 20
AAC decode and loop start: passed
visual boundary crossing after five seconds: passed
three labels and clear: passed
previous/next navigation: passed
JavaScript console errors: 0
```

スクリーンショット:

```text
artifacts/curated-seed-20260728-n60/review-chrome.png
```

最終の静的検査・テスト:

```text
ruff format --check: passed
ruff check: All checks passed!
pytest: 26 passed
```

## ラベル集計と閾値評価

利用者が2026-07-28 23:09:36 JSTまでに60曲すべてを判定した。

```text
loop: 27
loop_bad_points: 2
non_loop: 31
unlabeled: 0
```

評価コマンド:

```text
UV_CACHE_DIR=/private/tmp/endless-vgm-uv-cache \
uv run --project poc/stage1 stage1-evaluate \
  -a poc/stage1/artifacts/curated-seed-20260728-n60/analysis.json \
  -o poc/stage1/artifacts/curated-seed-20260728-n60/evaluation.json
```

終了コード: `0`

自動採用は、候補ありかつスコアが閾値以上とした。`loop`だけを正しい採用とし、
`non_loop`と`loop_bad_points`の採用を誤採用として数えた。

```text
threshold  false adoption  false exclusion  precision  recall
0.30       27              0                0.5000     1.0000
0.50       27              0                0.5000     1.0000
0.70       24              0                0.5294     1.0000
0.80       22              0                0.5510     1.0000
0.90       17              2                0.5952     0.9259
0.95       10              3                0.7059     0.8889
0.99       1               8                0.9500     0.7037
```

観測スコア境界を全探索した最小誤り:

```text
threshold           false adoption  false exclusion  total
0.9637638639661321  4               3                7
0.9733497968714576  3               4                7
```

曲末余白条件:

```text
maximum gap  loop  non_loop  loop_bad_points
3 seconds    0     0         0
5 seconds    0     0         1
10 seconds   4     1         1
15 seconds   10    4         2
```

5秒条件は正常ループを落とさず不正点1件を検出したが、もう1件の不正点は
曲末余白11.004秒だった。既知非ループ曲の分離には寄与しなかった。

成果物SHA-256:

```text
analysis.json:
d15d39e55f6dba3384d4f1246d7e34bbb1ab76b18350079d4df50d9ff0393a48
evaluation.json:
ddc6f3ed091028c4e6e0dbc730c450e923a2f190c3bb1b9718e100ce1f5f8ee8
review.csv:
f471bfa257c3f726b553fcd1ecd6a4535766f2505ecae9d7076e039306078c3f
```

評価器追加後の最終検査:

```text
ruff format: 1 file reformatted, 10 files left unchanged
ruff check: All checks passed!
pytest: 30 passed in 0.06s
```

## 再開検証

100曲完了後に同一コマンドを再実行した。

```text
process exit code: 0
analyzingログ: 0件
更新された曲別ログ: 0件
analysis.json SHA-256 before:
50011d3b5fd573077c57fa180caa9696117f81087c3eae647bbfa8ed50919c16
analysis.json SHA-256 after:
50011d3b5fd573077c57fa180caa9696117f81087c3eae647bbfa8ed50919c16
```

`review.csv`だけは既存の解析状態から再生成された。

## 未完了

- 単一スコア閾値を採用するかの利用者判断
