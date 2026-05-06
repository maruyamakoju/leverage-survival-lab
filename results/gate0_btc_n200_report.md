# Gate 0 Report — BTC (N=200 windows, 30-day each)

Cost model:
- taker fee = 0.040%
- per-leg slippage = 0.050%
- funding = injected from `data/raw/binance_BTCUSDT_funding.parquet`

Pass criteria (all three required):
- median annualized log-return > 0%
- Deflated Sharpe probability > 95% (Bonferroni n_trials = 75)
- 30-day bust rate (equity < 50% of initial) < 5%

## Gate 0 Pass Cells (0 / 75)

**No cell passed Gate 0.** This reinforces H3 (1x ですら手数料負けで負期待値) with funding now included. Either Gate 0 thresholds need to be reconsidered (and that change pre-registered), or no naive strategy in the current zoo is economically viable on BTC perp at low/mid leverage with realistic costs.

## All Cells (top 30 by annual log-return)

| Strategy | Lev | SL | TP | Med ann log-ret | DSR prob | Bust 30d | Final<50% | Liq | Gate 0 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| trend_filtered_sma | 3x | -5.00% | None | +26.71% | 0.000 | +9.05% | +4.02% | +0.00% | fail |
| trend_filtered_sma | 2x | -5.00% | None | +22.45% | 0.000 | +0.50% | +0.00% | +0.00% | fail |
| trend_filtered_sma | 5x | None | None | +19.41% | 0.000 | +39.20% | +24.62% | +19.60% | fail |
| breakout | 3x | None | None | +15.51% | 0.000 | +24.12% | +13.57% | +6.03% | fail |
| trend_filtered_sma | 3x | None | None | +13.97% | 0.000 | +20.60% | +11.56% | +6.53% | fail |
| trend_filtered_sma | 1x | -5.00% | None | +12.09% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| breakout | 2x | None | None | +10.36% | 0.000 | +10.05% | +5.53% | +2.51% | fail |
| trend_filtered_sma | 2x | None | None | +9.33% | 0.000 | +10.05% | +7.54% | +2.51% | fail |
| sma_cross | 1x | -5.00% | None | +5.32% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| breakout | 1x | None | None | +5.19% | 0.000 | +1.51% | +0.50% | +0.00% | fail |
| trend_filtered_sma | 1x | None | None | +4.67% | 0.000 | +1.51% | +1.01% | +0.00% | fail |
| sma_cross | 2x | -5.00% | None | +3.44% | 0.000 | +4.52% | +2.01% | +0.00% | fail |
| rsi | 1x | None | None | -1.09% | 0.000 | +5.03% | +1.51% | +0.50% | fail |
| rsi | 2x | None | None | -2.18% | 0.000 | +17.59% | +14.57% | +7.04% | fail |
| breakout | 1x | -5.00% | None | -2.41% | 0.000 | +0.50% | +0.50% | +0.00% | fail |
| sma_cross | 1x | None | None | -2.57% | 0.000 | +1.51% | +0.50% | +0.00% | fail |
| rsi | 3x | None | None | -3.27% | 0.000 | +29.65% | +20.60% | +14.57% | fail |
| sma_cross | 2x | None | None | -5.14% | 0.000 | +11.06% | +6.03% | +2.51% | fail |
| sma_cross | 3x | -5.00% | None | -5.68% | 0.000 | +17.09% | +9.05% | +0.00% | fail |
| sma_cross | 3x | None | None | -7.71% | 0.000 | +24.62% | +15.58% | +6.53% | fail |
| trend_filtered_sma | 1x | -2.00% | None | -8.87% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| breakout | 2x | -5.00% | None | -11.77% | 0.000 | +4.02% | +3.02% | +0.00% | fail |
| breakout | 1x | -2.00% | None | -12.21% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| bollinger | 1x | -2.00% | None | -12.61% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| rsi | 1x | -5.00% | None | -19.75% | 0.000 | +3.02% | +2.01% | +0.00% | fail |
| bollinger | 1x | None | None | -20.35% | 0.000 | +4.52% | +1.01% | +1.01% | fail |
| sma_cross | 1x | -2.00% | None | -20.68% | 0.000 | +0.00% | +0.00% | +0.00% | fail |
| rsi | 5x | None | None | -23.84% | 0.000 | +50.25% | +34.67% | +31.16% | fail |
| breakout | 5x | None | None | -24.67% | 0.000 | +47.24% | +28.14% | +25.63% | fail |
| bollinger | 1x | -5.00% | None | -24.83% | 0.000 | +1.01% | +0.00% | +0.00% | fail |