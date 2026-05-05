# Leverage Survival Lab — Report: real_btc_n500

## 概要

- 総シミュレーション数: **87,322**
- 戦略: bollinger, breakout, random, rsi, sma_cross
- レバレッジ水準: [np.float64(1.0), np.float64(2.0), np.float64(5.0), np.float64(10.0), np.float64(25.0), np.float64(50.0), np.float64(100.0)]
- 損切水準: [np.float64(-0.05), np.float64(-0.02), np.float64(-0.01), np.float64(-0.005)] + None
- データ識別子例: `win0_20200113`

## 仮説別サマリ

### H1 — 100倍レバ生存率は損切ルール問わず < 10%

| Strategy | Stop Loss | N | Survival | CI Upper | Violates H1 |
|----------|-----------|---|----------|----------|-------------|
| bollinger | -5.00% | 499 | 0.00% | 0.76% | no |
| bollinger | -2.00% | 499 | 0.00% | 0.76% | no |
| bollinger | -1.00% | 499 | 0.00% | 0.76% | no |
| bollinger | -0.50% | 499 | 0.00% | 0.76% | no |
| bollinger | None | 499 | 0.00% | 0.76% | no |
| breakout | -5.00% | 499 | 0.00% | 0.76% | no |
| breakout | -2.00% | 499 | 0.00% | 0.76% | no |
| breakout | -1.00% | 499 | 0.00% | 0.76% | no |
| breakout | -0.50% | 499 | 0.00% | 0.76% | no |
| breakout | None | 499 | 0.00% | 0.76% | no |
| random | -5.00% | 499 | 0.00% | 0.76% | no |
| random | -2.00% | 499 | 0.00% | 0.76% | no |
| random | -1.00% | 499 | 0.00% | 0.76% | no |
| random | -0.50% | 499 | 0.00% | 0.76% | no |
| random | None | 499 | 0.00% | 0.76% | no |
| rsi | -5.00% | 499 | 0.00% | 0.76% | no |
| rsi | -2.00% | 499 | 0.00% | 0.76% | no |
| rsi | -1.00% | 499 | 0.00% | 0.76% | no |
| rsi | -0.50% | 499 | 0.00% | 0.76% | no |
| rsi | None | 499 | 0.00% | 0.76% | no |
| sma_cross | -5.00% | 499 | 0.00% | 0.76% | no |
| sma_cross | -2.00% | 499 | 0.00% | 0.76% | no |
| sma_cross | -1.00% | 499 | 0.00% | 0.76% | no |
| sma_cross | -0.50% | 499 | 0.00% | 0.76% | no |
| sma_cross | None | 499 | 0.00% | 0.76% | no |

### H4 — 50x以上で戦略間の生存率有意差なし(粗集計)

| Lev | Strategy | Survival | CI |
|-----|----------|----------|----|
| 50x | bollinger | 0.00% | [0.00%, 0.76%] |
| 50x | bollinger | 0.00% | [0.00%, 0.76%] |
| 50x | bollinger | 0.00% | [0.00%, 0.76%] |
| 50x | bollinger | 0.00% | [0.00%, 0.76%] |
| 50x | bollinger | 0.00% | [0.00%, 0.76%] |
| 100x | bollinger | 0.00% | [0.00%, 0.76%] |
| 100x | bollinger | 0.00% | [0.00%, 0.76%] |
| 100x | bollinger | 0.00% | [0.00%, 0.76%] |
| 100x | bollinger | 0.00% | [0.00%, 0.76%] |
| 100x | bollinger | 0.00% | [0.00%, 0.76%] |
| 50x | breakout | 0.00% | [0.00%, 0.76%] |
| 50x | breakout | 0.00% | [0.00%, 0.76%] |
| 50x | breakout | 0.00% | [0.00%, 0.76%] |
| 50x | breakout | 0.00% | [0.00%, 0.76%] |
| 50x | breakout | 0.00% | [0.00%, 0.76%] |
| 100x | breakout | 0.00% | [0.00%, 0.76%] |
| 100x | breakout | 0.00% | [0.00%, 0.76%] |
| 100x | breakout | 0.00% | [0.00%, 0.76%] |
| 100x | breakout | 0.00% | [0.00%, 0.76%] |
| 100x | breakout | 0.00% | [0.00%, 0.76%] |
| 50x | random | 0.00% | [0.00%, 0.76%] |
| 50x | random | 0.00% | [0.00%, 0.76%] |
| 50x | random | 0.00% | [0.00%, 0.76%] |
| 50x | random | 0.00% | [0.00%, 0.76%] |
| 50x | random | 0.00% | [0.00%, 0.76%] |
| 100x | random | 0.00% | [0.00%, 0.76%] |
| 100x | random | 0.00% | [0.00%, 0.76%] |
| 100x | random | 0.00% | [0.00%, 0.76%] |
| 100x | random | 0.00% | [0.00%, 0.76%] |
| 100x | random | 0.00% | [0.00%, 0.76%] |
| 50x | rsi | 0.00% | [0.00%, 0.76%] |
| 50x | rsi | 0.00% | [0.00%, 0.76%] |
| 50x | rsi | 0.00% | [0.00%, 0.76%] |
| 50x | rsi | 0.00% | [0.00%, 0.76%] |
| 50x | rsi | 0.00% | [0.00%, 0.76%] |
| 100x | rsi | 0.00% | [0.00%, 0.76%] |
| 100x | rsi | 0.00% | [0.00%, 0.76%] |
| 100x | rsi | 0.00% | [0.00%, 0.76%] |
| 100x | rsi | 0.00% | [0.00%, 0.76%] |
| 100x | rsi | 0.00% | [0.00%, 0.76%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.76%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.76%] |

## 戦略別ヒートマップ

### bollinger

![bollinger](figures/real_btc_n500/heatmap_bollinger.png)

### breakout

![breakout](figures/real_btc_n500/heatmap_breakout.png)

### random

![random](figures/real_btc_n500/heatmap_random.png)

### rsi

![rsi](figures/real_btc_n500/heatmap_rsi.png)

### sma_cross

![sma_cross](figures/real_btc_n500/heatmap_sma_cross.png)

## レバ × 平均終端残高

| Lev | Mean Final Equity (USDT) | Median | % Bust |
|-----|-------------------------|--------|--------|
| 1x | 995,599 | 981,978 | 0.1% |
| 2x | 993,573 | 957,631 | 0.6% |
| 5x | 1,000,032 | 849,231 | 7.2% |
| 10x | 859,677 | 236,605 | 44.6% |
| 25x | 0 | 0 | 100.0% |
| 50x | 0 | 0 | 100.0% |
| 100x | 0 | 0 | 100.0% |

## 注釈・限界

- 本シミュレータは Isolated 単一ポジションを前提としている
- スリッページモデルは notional 比固定(深度ベースではない)
- 実データは Binance USDT-M Perp BTC/USDT のみ
- 結果は再現可能 (seed, params, commit hash) — 詳細は `docs/hypotheses.md`