# Stage-Gate 進捗 — Snapshot 2026-05-07

[stage_gate.md](stage_gate.md) のゲート定義に対する現状把握。**まだどのゲートも公式には通過していない**。

> **2026-05-07 update**:
> - Round 1 (`scripts/gate0_eval.py`, N=200, 5 戦略 × 5 lev × 3 SL = 75 cells): **0/75 PASS**
> - Round 2 (`scripts/gate0_round2.py`, trend_filtered_sma 単独 × window {30,90,180}d × 12 cells): **0/12 PASS × 全 window**
> - Gate 1 PREVIEW (`scripts/gate1_preview.py`, BTC/ETH/SOL × trend_filtered_sma × window 90d × 12 cells): **0/12 PASS × 全アセット** (ETH/SOL は funding なし、preview 限定)
> - Timeframe round (`scripts/gate0_round2_daily.py`, daily resample × {240,365,540} bars × 12 cells): **0/36 PASS**
> - Round 3 (`scripts/gate0_round3.py`, FundingFlipStrategy threshold=0.0003 × 12 cells, BTC 90d): **0/12 PASS** (median trades = 1 — signal threshold が高すぎ機能不全だが pre-reg 通り保持)
> - **総合**: SMA family + Funding family 両方 fail。現リポジトリの戦略では Gate 0 通過は不可能。
> - 詳細は本ドキュメント末尾を参照。

## Gate 0 現状

> 戦略単独で、コスト込みで期待値プラスか。

### バックテスト harness のコスト項

`src/leverage_survival_lab/engine/leverage.py` の `FeeModel`:

| コスト項目 | デフォルト値 | 備考 |
|---|---|---|
| Taker fee | 0.04% | Binance USDT-M Perp VIP0 想定。**現行レート 0.05% より低い** — Gate 0 では 0.05% に上げて再評価したい |
| Maker fee | 0.02% | bot は taker のみ使用 |
| Slippage (片道) | 0.05% | 1h 流動的銘柄でほぼ妥当。ストレス時は要 sensitivity test |
| Stop 追加 slippage | 0.05% | SL 約定時に上乗せ。妥当 |
| Round-trip cost (taker) | ≈ 0.18% | エントリー 0.09% + 退出 0.09%、SL なら +0.05% |

`LeverageEngine` は `total_fees` と `total_funding` を集計している。エンジン側のコスト
モデルは Gate 0 のための材料を持っている。

### Funding rate の扱い (重大ギャップ)

- `BacktestConfig.funding_rates: pd.Series | None = None` — **デフォルト `None` = funding rate 0**
- `src/leverage_survival_lab/backtest/grid.py` は `BacktestConfig(...)` を組むときに
  `funding_rates` を渡していない (grep 結果より) → **既存グリッド実行は funding を完全に無視している**
- `data/raw/binance_BTCUSDT_funding.parquet` は存在 → BTC の実 funding は手元にある
- ETH/SOL の funding parquet は不在

**含意**: 既存の H1-H4 結論は funding なしで出ている。100x 帯では関係ない (どっちみち1か月で
飛ぶ) が、Gate 0 評価対象の **低レバ帯ではこれは致命的な過大評価**。Binance BTC funding は
過去平均で約 0.01% / 8h ≈ 年率 11% 程度の追加コストで、1x ロング片張りに直接効く。

### 戦略カバレッジ

`src/leverage_survival_lab/strategies/`:

| 戦略 | クラス | バックテスト評価可能? | bot 実装? |
|---|---|---|---|
| random | RandomStrategy | ✓ | — |
| sma_cross | SMACrossStrategy | ✓ | — |
| rsi | RSIStrategy | ✓ | ✓ (V3.5+) |
| bollinger | BollingerStrategy | ✓ | — |
| breakout | BreakoutStrategy | ✓ | ✓ (momentum mode) |
| funding_flip | FundingFlipStrategy | ✓ (要 funding 注入) | — |
| trend_filtered_sma | TrendFilteredSMA | ✓ | ✓ (`trend_sma`, V3.9 commit `8bb4a52`) |

bot の `trend_sma` (20/50/200 SMA) はバックテストの `trend_filtered_sma` と
同一ロジックを共有している。Gate 0 評価はバックテスト側で実施可能。

### Gate 0 合否判定

**現時点で Gate 0 を通過した戦略は存在しない**。

- 過去のグリッド結果 (H3) は funding なしでも 1x で全戦略負け → funding を入れたらさらに悪化
- `trend_filtered_sma` を含む実用候補も funding 込みでの再評価未実施
- Deflated Sharpe / Risk of Ruin 指標は既存 analysis にあるが、Gate 0 の閾値で集計し直していない

## Gate 0 通過のための TODO (次セッションで着手)

1. **grid runner に funding rates を注入する経路を作る**
   - `BacktestConfig.funding_rates` に `binance_BTCUSDT_funding.parquet` を渡す
   - CLI / scripts から asset 指定で自動ロード
2. **FeeModel デフォルトを Binance 現行 (taker 0.05%) に更新するか検討**
   - 既存 H1-H4 の数値は変わらないので backward compatible (むしろ厳しい方向)
3. **全戦略 × {1, 2, 3, 5, 10}x で cost-aware backtest 再実行**
   - N≥500 ランダム30日窓
   - 出力: median annualized log-return, Deflated Sharpe (Bonferroni), Risk of Ruin (250d, equity<50%)
4. **Gate 0 通過戦略があるかの正式判定をこのドキュメントに追記**
   - 通れば Gate 1 (cross-asset) へ
   - 通らなければ「H3 の補強: 低レバ帯でも構造的にエッジなし」を pre-reg 通り公表

## Gate 1-5 現状

| Gate | 状況 |
|---|---|
| Gate 1 — cross-asset | 未着手。`scripts/codex_lowlev_cross_asset.py` (commit `32fc474`) が雛形だが未実行、funding 未注入 |
| Gate 2 — walk-forward / regime | walkforward harness 既存 (`backtest/walkforward.py`) だが Gate 2 の閾値で評価していない |
| Gate 3 — paper live 30 営業日 | 短時間 (V3.7+V3.8 = 6.3h, V3.9 trend_sma セッション開始) のみ。連続 30 日未達 |
| Gate 4 — オペレーション | kill switch / runbook / rate-limit 検証 未着手 |
| Gate 5 — 財務・心理 | 未定義。"失っても生活が回る額 X" のコミットなし |

## 結論

- Gate 0 が**通る戦略が一つも見つかっていない**段階。
- 実弾投入は Gate 0-5 すべて通った上で、本人が `CLAUDE.md` の「実弾0円」ルールを
  別コミットで撤回するまで行わない (これは [stage_gate.md](stage_gate.md) の上位ルール)。

## Gate 0 — Round 1 結果 (2026-05-07, BTC, N=200, funding 注入済)

スクリプト: `scripts/gate0_eval.py`
入力: `data/raw/binance_BTCUSDT_1h.parquet` + `binance_BTCUSDT_funding.parquet` (2020-01-01 〜 2026-05-05)
セル: 5 戦略 × 5 レバ × 3 SL × 1 TP = 75 cells、各 N=200 ランダム30日窓 (seed=20260507)
コスト: taker 0.04% + 片道 0.05% slippage + 実 funding rate (8h 刻み)

### 公式判定: **0 / 75 cells PASS**

3 条件 (median annual log-ret > 0 / DSR prob > 0.95 / 30d bust < 5%) を全て満たすセルは無し。

### DSR 失格は構造的問題 (要 pre-reg 改訂検討)

全 cells で `deflated_sharpe_prob ≈ 0`。サンプル Sharpe を見ると最良でも 0.36、
ほとんど負値。Bonferroni n_trials=75 を超えるには Sharpe > 2.4 程度必要だが、
30日 single window の cross-sectional sample で算出する Sharpe は性質上低くなる
(window 内 PnL volatility が大きい)。

これは Gate 0 の閾値設計が **window=30d だと事実上達成不可能** であることを意味する。
別コミットで [stage_gate.md](stage_gate.md) に注釈を追加し、round 2 で以下のいずれかを
検討する:
1. window を 90d / 180d に伸ばす (Sharpe を引き出しやすくする)
2. DSR の n_periods を年単位に正規化する (時系列としての Sharpe 計算)
3. DSR は維持しつつ、別のメタクライテリア (median return + bust rate) を二段階目に追加

### 観察: DSR 抜きの 2 条件パス cell

参考までに、median annual log-ret > 0 と 30d bust < 5% の 2 条件のみパスした 5 cells:

| Strategy | Lev | SL | Median ann log-ret | 30d bust | Median fees | Median funding |
|---|---:|---:|---:|---:|---:|---:|
| trend_filtered_sma | 1x | -5.0% | +12.09% | **+0.00%** | +0.32% | +0.02% |
| trend_filtered_sma | 1x | None | +4.67% | +1.51% | +0.09% | +0.02% |
| trend_filtered_sma | 2x | -5.0% | +22.45% | +0.50% | +0.64% | +0.05% |
| sma_cross | 1x | -5.0% | +5.32% | +0.00% | +0.32% | +0.03% |
| breakout | 1x | None | +5.19% | +1.51% | +0.09% | +0.06% |

これらは **公式 Gate 0 を通過していない**。あくまで「次にどこを攻めるかの示唆」。
`trend_filtered_sma` (= bot V3.9 `trend_sma` と同一ロジック) が低レバ × 強 SL で
funding 込みでも median +12〜22% をキープしている点は次ラウンドの起点になりうる。

### Round 1 から得られた含意

- **H3 部分修正**: 「1x ですら全戦略が手数料負け」だったのは旧グリッドで 6 戦略中
  `trend_filtered_sma` が含まれていなかったため。`trend_filtered_sma` 系は funding 込みでも
  低レバで median +。これは H3 の主張を弱めるので [hypotheses.md](hypotheses.md) の脚注に追記する価値あり (公開時)
- **bot V3.9 `trend_sma`** は単独評価ではバックテストで最も成績が良い。Gate 0 の DSR を
  通せていないが、cross-asset (Gate 1) で再現するか確認する優先度は高い
- **Bonferroni 補正の効きすぎ**: 75 cells を同時に評価する設計のままだと、
  どんな良い戦略でも DSR で叩き落とされる。round 2 では戦略を事前に 1 個固定 (n_trials=1) して
  確認する pre-reg を別途切る方が筋

### 出力ファイル
- `results/gate0_btc_n200.parquet` (15,000 sims raw)
- `results/gate0_btc_n200_summary.parquet` (75 cells aggregated)
- `results/gate0_btc_n200_report.md` (人間可読)

### 次のアクション

1. **pre-reg 改訂**: [stage_gate.md](stage_gate.md) に「DSR は window 期間/サンプル設計に強く
   依存する」注記を追加し、round 2 のメタクライテリア (例: 90d window) を追記する
2. **戦略事前固定 round**: `trend_filtered_sma` を**事前に1戦略**として固定し、n_trials=1 で
   DSR 評価する round を別途切る (Bonferroni を不要にする pre-reg を打つ)
3. **Gate 1 cross-asset preview**: ETH/SOL に対して同条件で評価し、`trend_filtered_sma` が
   BTC 偶然でないかの感触を見る (公式 Gate 1 評価ではないが round 2 の判断材料)

## Gate 0 — Round 2 結果 (2026-05-07, BTC, trend_filtered_sma 単独固定)

スクリプト: `scripts/gate0_round2.py`
Pre-reg: [stage_gate.md](stage_gate.md) Round 2 仕様 (commit `1062580`)
セル: trend_filtered_sma × 4 レバ × 3 SL = 12 cells、window={30,90,180}d、各 N=200。

### 公式判定: **3 window 全てで 0/12 PASS**

| window | n_cells | PASS | best cell | best median ann log-ret | best sample Sharpe |
|---|---:|---:|---|---:|---:|
| 30d | 12 | 0 | 3x SL=-5% | +26.7% | -0.08 |
| 90d | 12 | 0 | 3x SL=None | +102.7% | -0.85 |
| 180d | 12 | 0 | 2x SL=-2% | +15.5% | +0.20 |

### 重要な発見: sample Sharpe が構造的に < 1

DSR は全 window × 全 cell で prob ≈ 0。だがこれは Bonferroni の問題ではなく、
**trend_filtered_sma の生 Sharpe (annualized log-return ベース) が決して 1 を超えない** こと
が原因。最高でも window=90d, 1x SL=-2% で sample Sharpe = +0.64。

| window | top cell | sample Sharpe |
|---|---|---:|
| 30d | 1x SL=-5% | +0.36 |
| 90d | 1x SL=-2% | +0.64 |
| 180d | 1x SL=-2% | +0.38 |

n_trials=1 (Bonferroni を完全に外しても) の DSR 閾値は概ね Sharpe ≈ 0 だが、
**Gate 0 の意味のある運用には Sharpe > 1.0 (after-cost) は最低限必要**。
そこに届いていない以上、戦略選択や閾値の問題ではなく **エッジが弱い**ことが本質。

### Funding コストの window-length 依存性

| window | median funding cost (1x SL=-5%) |
|---|---:|
| 30d | +0.02% |
| 90d | +0.19% |
| 180d | +0.70% |

長期保有で funding が累積する。trend_filtered_sma は方向性ロング/ショートの保有が主で
funding の累積が効く。180d window では SL なし設定の cells が壊滅 (1x: -3.1%, 5x: -914%) する
最大要因が funding と方向逆転による累積損失。

### 結論: Gate 0 を通せる戦略は現状のリポジトリに無い

Round 1 (探索) と Round 2 (戦略単独確認) を経た結論:

- 6 戦略中 `trend_filtered_sma` が最も "見込みあり" だが、リターン/リスク比 (Sharpe) で
  Gate 0 を通せる水準ではない
- Bonferroni を外した n_trials=1 のもとでも、Sharpe ~ 0.6 では Gate 0 の DSR > 0.95 を
  通せない (DSR 0.95 ≈ Sharpe > 0 程度に緩むが、これは Gate 0 が想定する「本物のエッジ」と
  解釈するには弱い)
- これは [hypotheses.md](hypotheses.md) の H3「中レバで取引コストにより期待値マイナス」を
  funding 込みで部分的に支持する結果として記録できる

この時点で Gate 0 通過は事実上不可能。ただし以下の方向はまだ未検討:
1. **アセット軸の拡張**: ETH/SOL で BTC 偶然でないかを確認 (Gate 1 preview として)
2. **戦略族の刷新**: SMA 系を諦め、ボラ・センチメント・オーダーフロー・ファンディング逆張り
   などのファミリーを試す (新 pre-reg で Round 3 として切る)
3. **時間軸の変更**: 1h ではなく日足/週足、あるいはイントラデイ
4. **アンサンブル**: 複数戦略のシグナル合成 (ただし Bonferroni 注意)

実弾モードへの移行は **明確に現状の戦略群では正当化されない**。
これは [stage_gate.md](stage_gate.md) 上位ルール 1 の「全ゲート通過まで実弾0円」を強く支える証拠。

### 出力ファイル
- `results/gate0_round2_btc_w{30,90,180}_n200.parquet` (raw, 各 2,400 sims)
- `results/gate0_round2_btc_w{30,90,180}_n200_summary.parquet` (各 12 cells)
- `results/gate0_round2_btc_n200_report.md` (人間可読、3 window まとめ)

## Gate 1 PREVIEW (cross-asset, 公式評価ではない)

スクリプト: `scripts/gate1_preview.py` (window=90d, N=200, trend_filtered_sma 単独)

> **PREVIEW 限定の理由**: 本環境では ccxt が Binance に到達できず ETH/SOL の funding rate を
> 取得できなかった。BTC は実 funding 注入、ETH/SOL は funding なし (上方バイアスあり)。
> 本評価は公式 Gate 1 として扱わず、判断材料 (preview) のみとする。

### 結果サマリ (PASS は全アセットで 0/12)

各アセットの上位 cell:

| Asset | Top cell | Median ann log-ret | Sample Sharpe | Bust(90d) |
|---|---|---:|---:|---:|
| BTC (funding YES) | 1x SL=-5% | +19.15% | **+0.57** | 0.00% |
| ETH (funding NO) | 2x SL=-5% | +25.34% | -0.19 | 27.00% |
| SOL (funding NO) | 1x SL=-5% | +60.14% | **+0.63** | 13.57% |

### 重要観察: アセット間で Sharpe が一貫しない

`1x SL=-5%` (BTC で最良 Sharpe を出した cell) を 3 アセットで比較:

| Asset | Median ann log-ret | Sample Sharpe | Bust |
|---|---:|---:|---:|
| BTC | +19.15% | **+0.57** | 0.00% |
| ETH | +16.32% | **-0.18** | 6.50% |
| SOL | +60.14% | **+0.63** | 13.57% |

ETH で Sharpe がマイナスに沈む。これは戦略のエッジが **アセット特性 (ボラ・トレンド構造) に
強く依存** することを意味し、Gate 1 が要求する「同パラメータで複数アセットを robustly 通す」
という条件を、preview の段階で既に満たさない。

### Cross-asset 最悪ケースの最大値 (worst-asset performance)

各 cell について 3 アセットの最低値を見ると:

- 1x SL=-5%: 最低 ETH +16.32% / 最低 ETH Sharpe -0.18
- 2x SL=-5%: 最低 BTC +29.39% / 最低 ETH Sharpe -0.19
- 1x SL=None: 最低 ETH +7.18% / 最低 ETH Sharpe -0.43
- 5x cells: 多数のアセットで爆損 (SOL/ETH no-SL で -8400% など — 完全破綻)

**全アセットで Sharpe > 0 を満たす cell は 0 件**。Gate 1 の本式評価でも (funding 込みなら
さらに悪化するため) 通る見込みは無い。

### 出力ファイル
- `results/gate1_preview_{BTC,ETH,SOL}_n200.parquet` (raw)
- `results/gate1_preview_{BTC,ETH,SOL}_n200_summary.parquet`
- `results/gate1_preview_n200_report.md`

## Timeframe Round (2026-05-07, BTC daily resample)

スクリプト: `scripts/gate0_round2_daily.py` (1h を 1d に resample)
window_bars = {240, 365, 540} = {8ヶ月, 1年, 1.5年}、各 N=200

### 結果: 0/36 PASS

| window | top cell | Median ann log-ret | Sample Sharpe | Bust |
|---|---|---:|---:|---:|
| 240d | 1x SL=None | +2.42% | +0.15 | 1.05% |
| 365d | 1x SL=-5% | +2.11% | +0.06 | 12.63% |
| 540d | 3x SL=None | +31.00% | -0.59 | 58.55% |

Daily でも Sharpe は最良 +0.15。長期保有で no-SL 5x cells は完全破綻
(365d 5x no-SL: median -2074%)。

## Gate 0 Round 3 (2026-05-07, BTC, FundingFlipStrategy)

スクリプト: `scripts/gate0_round3.py`
Pre-reg: stage_gate.md Round 3 (commit `ba2f7f8`)
パラメータ: threshold=0.0003 (年率約33% funding), lookback=24

### 結果: 0/12 PASS (うち戦略機能不全)

| Lev | SL | Median ann log-ret | Sample Sharpe | Bust(90d) | Median trades |
|---:|---:|---:|---:|---:|---:|
| 1x | -5% | +0.00% | -0.60 | 8.0% | **1** |
| 1x | None | +0.00% | -0.63 | 12.6% | 1 |
| 5x | None | +0.00% | -0.92 | 39.2% | 1 |

**重要観察**: Median trades = 1 件 / 90d window。FundingFlip の threshold=0.0003
(年率33% funding) は Binance BTC funding の実分布の極端側に位置し、90日間で signal が
ほぼ立たない。事実上「機能していない」状態。

**pre-reg 遵守判断**: threshold は事前固定済みなので、シグナルが出ないことも結果として保持。
threshold を後から下げて再評価するのは pre-reg 違反。Round 4 で別 pre-reg を切る場合のみ
パラメータ調整可。

ただ threshold=0.0003 は funding_filter.py のクラスデフォルト値であり、設計時にどの程度の
極端性を想定していたかは曖昧。Round 4 を切るなら threshold={0.0001, 0.0002} 程度の
よりよく発火する閾値を試す価値あり (これは新 pre-reg)。

## 総合結論 (2026-05-07 終了時)

5 ラウンド (Round 1, Round 2, Gate 1 preview, Timeframe round, Round 3) の結果:

| Round | 対象 | PASS / 評価 cells |
|---|---|---:|
| Round 1 | 5 strategies × 75 cells, BTC 1h, funding 込み | 0 / 75 |
| Round 2 | trend_filtered_sma × {30,90,180}d × 12 cells, BTC 1h | 0 / 36 |
| Gate 1 preview | trend_filtered_sma cross-asset (BTC funding込み, ETH/SOL なし) | 0 / 36 |
| Timeframe round | trend_filtered_sma × daily × {240,365,540}bars | 0 / 36 |
| Round 3 | FundingFlipStrategy 90d × 12 cells, BTC 1h | 0 / 12 |
| **合計** | | **0 / 195** |

**結論**:
- 現リポジトリの 6 戦略 (random / sma_cross / rsi / bollinger / breakout / trend_filtered_sma /
  funding_flip) は **どれも Gate 0 を通せない**
- これは戦略のチューニングや multiple testing の問題ではない:
  - SMA family: 生 Sharpe が構造的に < 1
  - FundingFlip: threshold が極端で signal がほぼ立たない (Round 4 で再評価可)
- 実弾投入は **明確に正当化されない**。`CLAUDE.md` の「実弾0円」ルールは
  5 ラウンド分のエビデンスで強化済み

### 次の選択肢

1. **Round 4 — FundingFlip の threshold 調整 + 派生戦略**: threshold={0.0001, 0.0002} で
   再評価 (新 pre-reg)。さらに ボラ breakout / オーダーフロー系を追加検証
2. **撤退・公開**: 現状の 5 ラウンド分のエビデンスをまとめて blog / twitter で発信
   (V7: 「Stage-Gate を通したら全戦略 fail だった話」)。pre-reg ルール 4 通りの正規の研究成果
3. **両方並行**: Round 4 を準備しつつ V7 blog 下書きを完成させる

実弾モードへの移行は **5 ラウンドのデータで明確に否定されている**。
実弾0円ルールの撤回はこのデータが覆らない限りあり得ない。
