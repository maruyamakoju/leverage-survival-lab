# Stage-Gate 進捗 — Snapshot 2026-05-07

[stage_gate.md](stage_gate.md) のゲート定義に対する現状把握。**まだどのゲートも公式には通過していない**。

> **2026-05-07 update**: 第1回 Gate 0 評価を BTC で実行 (`scripts/gate0_eval.py`、N=200)。
> 結果: **0 / 75 cells が公式 Gate 0 通過**。
> 詳細は本ドキュメント末尾「Gate 0 — Round 1 結果」を参照。

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
