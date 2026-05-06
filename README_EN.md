# Leverage Survival Lab

> **Does "100x leverage with stop loss" actually work?** — verified across 269,963 Monte Carlo backtests on real BTC/USDT data.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)

[日本語版 README はこちら](README.md)

![hero heatmap](results/figures/hero_heatmap.png)

## TL;DR

We sampled **~1,800 random 30-day windows** from 6+ years of Binance USDT-M Perpetual BTC/USDT 1-hour bars (2020-01–2026-05) and ran **269,963 Monte Carlo backtests** across 5 strategies × 7 leverage levels × 5 stop-loss tiers.

**Findings**:

- **100x leverage 30-day survival rate = 0%.** 95% Wilson CI upper bound: **0.27%**
- Result holds across all stop-loss levels (-0.5% to -5%, or none)
- **Result holds across BTC / ETH / SOL** (the three largest perpetual-swap majors)
- **Reducing position size to 5% of equity does not save 100x** — accumulated losses still kill the account
- Holds across all market regimes (trend up, range, crash)
- At ≥50x leverage, no statistically significant difference between naive strategies and random entry (Bonferroni-corrected)

The narrative "100x leverage works with proper stop loss" is rejected by the data.

### 2026-05-07 update — Stage-Gate protocol: 0 / 195 cells pass

To stop "what if I quietly slip in real money once an edge shows up" from running my brain,
I pre-registered a six-stage gate ([docs/stage_gate.md](docs/stage_gate.md)) and ran five
cost-aware backtest rounds in one day. Every round failed.

| Round | Scope | Pass / cells |
|---|---|---:|
| Round 1 | 5 strategies × 75 cells, BTC 1h, funding included | 0 / 75 |
| Round 2 | trend_filtered_sma alone × 3 windows × 12 cells | 0 / 36 |
| Gate 1 preview | trend_filtered_sma cross-asset (BTC/ETH/SOL) | 0 / 36 |
| Timeframe round | trend_filtered_sma × daily × 3 windows | 0 / 36 |
| Round 3 | FundingFlipStrategy 90d × 12 cells | 0 / 12 |
| **Total** | | **0 / 195** |

Key findings:
- trend_filtered_sma's after-cost sample sharpe peaks at **+0.64** — far below the >1
  needed for real trading
- The cell with sharpe +0.57 on BTC drops to **-0.18 on ETH**. Edge is asset-conditional.
- Daily resample tops at sharpe +0.15. Timeframe doesn't save it.
- FundingFlip threshold=0.0003 is in the tail of actual funding distribution; signal
  fires only once per 90d on average (effectively broken, kept per pre-reg)

Conclusion: no strategy in this repo justifies real-money trading.
See [docs/stage_gate_status.md](docs/stage_gate_status.md) for the full snapshot and
[docs/blog_draft_v7_stage_gate.md](docs/blog_draft_v7_stage_gate.md) for the long write-up.

## Pre-registered hypotheses

To prevent post-hoc cherry-picking, we pre-registered 4 hypotheses in [docs/hypotheses.md](docs/hypotheses.md), locked at git commit `4694ff0` (2026-05-05).

| Hypothesis | Result | Headline number |
|------------|--------|-----------------|
| **H1**: 100x 30d survival < 10% regardless of stop loss | **Strongly supported** | 0/25 cells violate, **CI upper 0.27%** |
| **H2**: Optimal stop-loss is interior (not boundary) | Partially supported | Interior solutions only at mid-leverage (5x, 10x) |
| **H3**: Strategy edge dies at 10–20x | **Measurable (partially supported)** | `trend_filtered_sma` crossover: ~10-15x by mean equity, ~3-5x by log-return |
| **H4**: ≥50x has no strategy advantage | **Supported** | All 8 comparisons: p > 0.00625 |

Full report: [`results/hypothesis_test_real_btc_n2000.md`](results/hypothesis_test_real_btc_n2000.md)

## Why a custom simulator (and not vectorbt etc.)?

1. **Liquidation is checked on intra-bar high/low**, not just close (otherwise liquidations are missed)
2. **Maker/taker fees + slippage applied per side**, with extra slippage on stop fills
3. **Funding rate** applied every 8h from the actual Binance funding history
4. **Look-ahead bias prevention**: signals at bar t close → fills at bar t+1 open, enforced at engine level
5. **Equity clamped at 0** in isolated margin (otherwise small fee residual makes equity negative)
6. **Multiple-comparison correction**: Bonferroni / BH-FDR / Deflated Sharpe

## Quickstart

```bash
python -m venv .venv
. .venv/Scripts/activate          # Windows PowerShell
pip install -e ".[dev]"

# 1. Fetch data (~2 min)
python -m leverage_survival_lab.data.fetch ohlcv \
  --symbol BTC/USDT --tf 1h --since 2020-01-01

# 2. Mini smoke test on synthetic data
python scripts/run_mini_experiment.py

# 3. Real-data experiment (N=500, ~2 min, 87k sims)
python scripts/run_realdata_experiment.py --n-windows 500 --name my_run

# 4. Hypothesis testing + report
python scripts/test_hypotheses.py --input results/grid_my_run.parquet --name my_run
python scripts/generate_report.py --input results/grid_my_run.parquet --name my_run

# 5. Tests
pytest -W ignore::RuntimeWarning
```

## Limitations

- Single asset (BTC/USDT), single venue (Binance USDT-M Perp)
- Slippage is fixed-percentage (not order-book-depth based)
- Cross-margin engine is implemented but not yet tested at scale
- This is observational — not a claim that all leverage trading is bad. We're saying: at 100x, no naive strategy survives 30 days.

## Disclaimer

- This is **not investment advice**.
- Simulation results do not guarantee real-trade outcomes.
- API access is read-only and rate-limited per exchange ToS.

## License

[MIT](LICENSE) — fork it, re-run it, contradict our findings.

## Author

[@maruyamakoju](https://github.com/maruyamakoju) — Japanese freelance engineer working at the intersection of AI agents and quantitative finance.

> Built collaboratively with [Claude Code](https://claude.com/claude-code) — most of the implementation, experimentation, and analysis was driven autonomously by the agent.
