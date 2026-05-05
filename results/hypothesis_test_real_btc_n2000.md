# Hypothesis Test Report — real_btc_n2000

## H1 — 100x leverage 30日生存率 < 10%
- Supported: **True**
- Cells violating: 0 / 25
- Max CI upper bound: 0.0027

```
 strategy  stop_loss    n  survival    ci_hi  violates_h1
bollinger     -0.050 1400       0.0 0.002736        False
bollinger     -0.020 1400       0.0 0.002736        False
bollinger     -0.010 1400       0.0 0.002736        False
bollinger     -0.005 1400       0.0 0.002736        False
bollinger        NaN 1400       0.0 0.002736        False
 breakout     -0.050 1400       0.0 0.002736        False
 breakout     -0.020 1400       0.0 0.002736        False
 breakout     -0.010 1400       0.0 0.002736        False
 breakout     -0.005 1400       0.0 0.002736        False
 breakout        NaN 1400       0.0 0.002736        False
   random     -0.050 1400       0.0 0.002736        False
   random     -0.020 1400       0.0 0.002736        False
   random     -0.010 1400       0.0 0.002736        False
   random     -0.005 1400       0.0 0.002736        False
   random        NaN 1400       0.0 0.002736        False
      rsi     -0.050 1400       0.0 0.002736        False
      rsi     -0.020 1400       0.0 0.002736        False
      rsi     -0.010 1400       0.0 0.002736        False
      rsi     -0.005 1400       0.0 0.002736        False
      rsi        NaN 1400       0.0 0.002736        False
sma_cross     -0.050 1400       0.0 0.002736        False
sma_cross     -0.020 1400       0.0 0.002736        False
sma_cross     -0.010 1400       0.0 0.002736        False
sma_cross     -0.005 1400       0.0 0.002736        False
sma_cross        NaN 1400       0.0 0.002736        False
```

## H2 — 各レバ倍率に最適な損切ラインが内点解として存在
- Interior solution rate: 14.3%

```
 strategy  leverage  best_stop_loss  best_survival  interior
bollinger       1.0          -0.005       1.000000     False
bollinger       2.0          -0.005       1.000000     False
bollinger       5.0          -0.005       0.971875     False
bollinger      10.0          -0.020       0.689286      True
bollinger      25.0          -0.005       0.000000     False
bollinger      50.0          -0.005       0.000000     False
bollinger     100.0          -0.005       0.000000     False
 breakout       1.0          -0.005       1.000000     False
 breakout       2.0          -0.005       1.000000     False
 breakout       5.0          -0.005       1.000000     False
 breakout      10.0          -0.010       0.867857      True
 breakout      25.0          -0.005       0.000000     False
 breakout      50.0          -0.005       0.000000     False
 breakout     100.0          -0.005       0.000000     False
   random       1.0          -0.005       1.000000     False
   random       2.0          -0.005       1.000000     False
   random       5.0          -0.005       0.997500     False
   random      10.0          -0.005       0.811250     False
   random      25.0          -0.005       0.000000     False
   random      50.0          -0.005       0.000000     False
   random     100.0          -0.005       0.000000     False
      rsi       1.0          -0.005       1.000000     False
      rsi       2.0          -0.005       1.000000     False
      rsi       5.0          -0.010       0.968750      True
      rsi      10.0          -0.005       0.711250     False
      rsi      25.0          -0.005       0.000000     False
      rsi      50.0          -0.005       0.000000     False
      rsi     100.0          -0.005       0.000000     False
sma_cross       1.0          -0.005       1.000000     False
sma_cross       2.0          -0.005       1.000000     False
sma_cross       5.0          -0.020       0.981875      True
sma_cross      10.0          -0.010       0.793553      True
sma_cross      25.0          -0.005       0.000000     False
sma_cross      50.0          -0.005       0.000000     False
sma_cross     100.0          -0.005       0.000000     False
```

## H3 — 戦略エッジが消失する閾値レバ
```
 strategy  crossover_leverage  mean_log_ret_lev1
bollinger                 NaN          -0.045052
 breakout                 2.0           0.000131
   random                 NaN          -0.017185
      rsi                 NaN          -0.034558
sma_cross                 NaN          -0.009731
```

## H4 — 50x以上でナイーブ戦略 vs ランダム の有意差なし(Bonferroni 補正)
- Supported (no significant difference): **True**
- Adjusted α: 0.00625

```
 leverage  strategy  p_strategy  p_random   z  p_value  reject_null
     50.0 sma_cross         0.0       0.0 0.0      1.0        False
     50.0       rsi         0.0       0.0 0.0      1.0        False
     50.0 bollinger         0.0       0.0 0.0      1.0        False
     50.0  breakout         0.0       0.0 0.0      1.0        False
    100.0 sma_cross         0.0       0.0 0.0      1.0        False
    100.0       rsi         0.0       0.0 0.0      1.0        False
    100.0 bollinger         0.0       0.0 0.0      1.0        False
    100.0  breakout         0.0       0.0 0.0      1.0        False
```
