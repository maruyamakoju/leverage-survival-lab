# Hypothesis Test Report — real_btc_n2000

## H1 — 100x leverage 30日生存率 < 10%
- Supported: **True**
- Cells violating: 0 / 25
- Max CI upper bound: 0.0048

```
 strategy  stop_loss   n  survival    ci_hi  violates_h1
bollinger     -0.050 800       0.0 0.004779        False
bollinger     -0.020 800       0.0 0.004779        False
bollinger     -0.010 800       0.0 0.004779        False
bollinger     -0.005 800       0.0 0.004779        False
bollinger        NaN 800       0.0 0.004779        False
 breakout     -0.050 800       0.0 0.004779        False
 breakout     -0.020 800       0.0 0.004779        False
 breakout     -0.010 800       0.0 0.004779        False
 breakout     -0.005 800       0.0 0.004779        False
 breakout        NaN 800       0.0 0.004779        False
   random     -0.050 800       0.0 0.004779        False
   random     -0.020 800       0.0 0.004779        False
   random     -0.010 800       0.0 0.004779        False
   random     -0.005 800       0.0 0.004779        False
   random        NaN 800       0.0 0.004779        False
      rsi     -0.050 800       0.0 0.004779        False
      rsi     -0.020 800       0.0 0.004779        False
      rsi     -0.010 800       0.0 0.004779        False
      rsi     -0.005 800       0.0 0.004779        False
      rsi        NaN 800       0.0 0.004779        False
sma_cross     -0.050 800       0.0 0.004779        False
sma_cross     -0.020 800       0.0 0.004779        False
sma_cross     -0.010 800       0.0 0.004779        False
sma_cross     -0.005 800       0.0 0.004779        False
sma_cross        NaN 800       0.0 0.004779        False
```

## H2 — 各レバ倍率に最適な損切ラインが内点解として存在
- Interior solution rate: 14.3%

```
 strategy  leverage  best_stop_loss  best_survival  interior
bollinger       1.0          -0.005        1.00000     False
bollinger       2.0          -0.005        1.00000     False
bollinger       5.0          -0.005        0.97375     False
bollinger      10.0          -0.020        0.68250      True
bollinger      25.0          -0.005        0.00000     False
bollinger      50.0          -0.005        0.00000     False
bollinger     100.0          -0.005        0.00000     False
 breakout       1.0          -0.005        1.00000     False
 breakout       2.0          -0.005        1.00000     False
 breakout       5.0          -0.005        1.00000     False
 breakout      10.0          -0.010        0.86500      True
 breakout      25.0          -0.005        0.00000     False
 breakout      50.0          -0.005        0.00000     False
 breakout     100.0          -0.005        0.00000     False
   random       1.0          -0.005        1.00000     False
   random       2.0          -0.005        1.00000     False
   random       5.0          -0.005        0.99625     False
   random      10.0          -0.005        0.81000     False
   random      25.0          -0.005        0.00000     False
   random      50.0          -0.005        0.00000     False
   random     100.0          -0.005        0.00000     False
      rsi       1.0          -0.005        1.00000     False
      rsi       2.0          -0.005        1.00000     False
      rsi       5.0          -0.010        0.97375      True
      rsi      10.0          -0.005        0.72250     False
      rsi      25.0          -0.005        0.00000     False
      rsi      50.0          -0.005        0.00000     False
      rsi     100.0          -0.005        0.00000     False
sma_cross       1.0          -0.005        1.00000     False
sma_cross       2.0          -0.005        1.00000     False
sma_cross       5.0          -0.020        0.98125      True
sma_cross      10.0          -0.010        0.79250      True
sma_cross      25.0          -0.005        0.00000     False
sma_cross      50.0          -0.005        0.00000     False
sma_cross     100.0          -0.005        0.00000     False
```

## H3 — 戦略エッジが消失する閾値レバ
```
 strategy crossover_leverage  mean_log_ret_lev1
bollinger               None          -0.037936
 breakout               None          -0.002336
   random               None          -0.015879
      rsi               None          -0.032708
sma_cross               None          -0.011869
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
