# Leverage Survival Lab — Report: real_btc_n2000

## 概要

- 総シミュレーション数: **269,963**
- 戦略: bollinger, breakout, random, rsi, sma_cross
- レバレッジ水準: [np.float64(1.0), np.float64(2.0), np.float64(5.0), np.float64(10.0), np.float64(25.0), np.float64(50.0), np.float64(100.0)]
- 損切水準: [np.float64(-0.05), np.float64(-0.02), np.float64(-0.01), np.float64(-0.005)] + None
- データ識別子例: `win0_20200301`

## 仮説別サマリ

### H1 — 100倍レバ生存率は損切ルール問わず < 10%

| Strategy | Stop Loss | N | Survival | CI Upper | Violates H1 |
|----------|-----------|---|----------|----------|-------------|
| bollinger | -5.00% | 1400 | 0.00% | 0.27% | no |
| bollinger | -2.00% | 1400 | 0.00% | 0.27% | no |
| bollinger | -1.00% | 1400 | 0.00% | 0.27% | no |
| bollinger | -0.50% | 1400 | 0.00% | 0.27% | no |
| bollinger | None | 1400 | 0.00% | 0.27% | no |
| breakout | -5.00% | 1400 | 0.00% | 0.27% | no |
| breakout | -2.00% | 1400 | 0.00% | 0.27% | no |
| breakout | -1.00% | 1400 | 0.00% | 0.27% | no |
| breakout | -0.50% | 1400 | 0.00% | 0.27% | no |
| breakout | None | 1400 | 0.00% | 0.27% | no |
| random | -5.00% | 1400 | 0.00% | 0.27% | no |
| random | -2.00% | 1400 | 0.00% | 0.27% | no |
| random | -1.00% | 1400 | 0.00% | 0.27% | no |
| random | -0.50% | 1400 | 0.00% | 0.27% | no |
| random | None | 1400 | 0.00% | 0.27% | no |
| rsi | -5.00% | 1400 | 0.00% | 0.27% | no |
| rsi | -2.00% | 1400 | 0.00% | 0.27% | no |
| rsi | -1.00% | 1400 | 0.00% | 0.27% | no |
| rsi | -0.50% | 1400 | 0.00% | 0.27% | no |
| rsi | None | 1400 | 0.00% | 0.27% | no |
| sma_cross | -5.00% | 1400 | 0.00% | 0.27% | no |
| sma_cross | -2.00% | 1400 | 0.00% | 0.27% | no |
| sma_cross | -1.00% | 1400 | 0.00% | 0.27% | no |
| sma_cross | -0.50% | 1400 | 0.00% | 0.27% | no |
| sma_cross | None | 1400 | 0.00% | 0.27% | no |

### H4 — 50x以上で戦略間の生存率有意差なし(粗集計)

| Lev | Strategy | Survival | CI |
|-----|----------|----------|----|
| 50x | bollinger | 0.00% | [0.00%, 0.27%] |
| 50x | bollinger | 0.00% | [0.00%, 0.27%] |
| 50x | bollinger | 0.00% | [0.00%, 0.27%] |
| 50x | bollinger | 0.00% | [0.00%, 0.27%] |
| 50x | bollinger | 0.00% | [0.00%, 0.27%] |
| 100x | bollinger | 0.00% | [0.00%, 0.27%] |
| 100x | bollinger | 0.00% | [0.00%, 0.27%] |
| 100x | bollinger | 0.00% | [0.00%, 0.27%] |
| 100x | bollinger | 0.00% | [0.00%, 0.27%] |
| 100x | bollinger | 0.00% | [0.00%, 0.27%] |
| 50x | breakout | 0.00% | [0.00%, 0.27%] |
| 50x | breakout | 0.00% | [0.00%, 0.27%] |
| 50x | breakout | 0.00% | [0.00%, 0.27%] |
| 50x | breakout | 0.00% | [0.00%, 0.27%] |
| 50x | breakout | 0.00% | [0.00%, 0.27%] |
| 100x | breakout | 0.00% | [0.00%, 0.27%] |
| 100x | breakout | 0.00% | [0.00%, 0.27%] |
| 100x | breakout | 0.00% | [0.00%, 0.27%] |
| 100x | breakout | 0.00% | [0.00%, 0.27%] |
| 100x | breakout | 0.00% | [0.00%, 0.27%] |
| 50x | random | 0.00% | [0.00%, 0.27%] |
| 50x | random | 0.00% | [0.00%, 0.27%] |
| 50x | random | 0.00% | [0.00%, 0.27%] |
| 50x | random | 0.00% | [0.00%, 0.27%] |
| 50x | random | 0.00% | [0.00%, 0.27%] |
| 100x | random | 0.00% | [0.00%, 0.27%] |
| 100x | random | 0.00% | [0.00%, 0.27%] |
| 100x | random | 0.00% | [0.00%, 0.27%] |
| 100x | random | 0.00% | [0.00%, 0.27%] |
| 100x | random | 0.00% | [0.00%, 0.27%] |
| 50x | rsi | 0.00% | [0.00%, 0.27%] |
| 50x | rsi | 0.00% | [0.00%, 0.27%] |
| 50x | rsi | 0.00% | [0.00%, 0.27%] |
| 50x | rsi | 0.00% | [0.00%, 0.27%] |
| 50x | rsi | 0.00% | [0.00%, 0.27%] |
| 100x | rsi | 0.00% | [0.00%, 0.27%] |
| 100x | rsi | 0.00% | [0.00%, 0.27%] |
| 100x | rsi | 0.00% | [0.00%, 0.27%] |
| 100x | rsi | 0.00% | [0.00%, 0.27%] |
| 100x | rsi | 0.00% | [0.00%, 0.27%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 50x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.27%] |
| 100x | sma_cross | 0.00% | [0.00%, 0.27%] |

## 戦略別ヒートマップ

### bollinger

![bollinger](figures/real_btc_n2000/heatmap_bollinger.png)

### breakout

![breakout](figures/real_btc_n2000/heatmap_breakout.png)

### random

![random](figures/real_btc_n2000/heatmap_random.png)

### rsi

![rsi](figures/real_btc_n2000/heatmap_rsi.png)

### sma_cross

![sma_cross](figures/real_btc_n2000/heatmap_sma_cross.png)

## レバ × 平均終端残高

| Lev | Mean Final Equity (USDT) | Median | % Bust |
|-----|-------------------------|--------|--------|
| 1x | 999,143 | 985,781 | 0.0% |
| 2x | 1,000,028 | 964,322 | 0.6% |
| 5x | 1,016,201 | 868,326 | 7.3% |
| 10x | 899,642 | 290,057 | 42.9% |
| 25x | 0 | 0 | 100.0% |
| 50x | 0 | 0 | 100.0% |
| 100x | 0 | 0 | 100.0% |

## 注釈・限界

- 本シミュレータは Isolated 単一ポジションを前提としている
- スリッページモデルは notional 比固定(深度ベースではない)
- 実データは Binance USDT-M Perp BTC/USDT のみ
- 結果は再現可能 (seed, params, commit hash) — 詳細は `docs/hypotheses.md`