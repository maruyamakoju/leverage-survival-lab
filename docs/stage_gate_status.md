# Stage-Gate 進捗 — Snapshot 2026-05-07

[stage_gate.md](stage_gate.md) のゲート定義に対する現状把握。**まだどのゲートも公式には通過していない**。

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
- 次の作業: funding を grid に注入して、cost-aware Gate 0 評価を BTC 単体で回す。
