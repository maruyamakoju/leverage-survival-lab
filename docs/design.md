# 設計ノート — Leverage Survival Lab

## レバレッジエンジンの数式

### 1. 用語

| 記号       | 意味                                                |
|-----------|---------------------------------------------------|
| `eq_t`    | 時刻 t の口座エクイティ(USDT)                     |
| `pos_t`   | 時刻 t のポジション数量(契約数、long=正/short=負) |
| `entry`   | エントリー価格                                       |
| `p_t`     | 時刻 t の参照価格(マーク or 取引価格)             |
| `L`       | レバレッジ倍率(初期 IM = notional/L)              |
| `mm`      | 維持証拠金率(Binance USDT-M Perp の階層に従う)   |
| `f_t`     | テイカー手数料率(片道、約定 notional に対し)      |
| `f_m`     | メイカー手数料率                                    |
| `s`       | スリッページ率(片道、notional に対し)             |
| `r_fund`  | ファンディングレート(8h ごと、long支払い=正)     |

### 2. 清算価格(Isolated Margin, USDT-M Perpetual)

ロングポジションの清算価格 `p_liq` は、未実現損が initial_margin - maintenance_margin を超えた点:

```
notional   = entry * |pos|
im         = notional / L
mm_amount  = notional * mm
loss_to_liq = im - mm_amount

# Long
p_liq_long  = entry - loss_to_liq / |pos|
            = entry * (1 - 1/L + mm)
# Short
p_liq_short = entry * (1 + 1/L - mm)
```

> Cross margin の場合は口座全体のエクイティを参照。本実装では Isolated と Cross の両モードを `MarginMode` enum で切替。

### 3. PnL とエクイティ更新

各バー `t`(または各 trade event)で:

```
unrealized_pnl_t = pos * (p_t - entry)               # 数量×価格差
realized_pnl     = pos * (exit - entry) - fees - slip
funding_pmt_t    = pos * mark_t * r_fund_t           # long が正なら支払い
eq_t = eq_{t-1} + Δrealized - Δfees - Δslip - Δfunding
```

### 4. 約定モデル

- **Market order**: 次バーの **Open** で約定、テイカー手数料+スリッページ
- **Stop loss**: 当該バーの High/Low が SL 価格に触れたら **SL 価格**で約定(楽観的)+ 0.05% 追加スリッページ(ペシミスティック)
- **Liquidation**: 当該バーの High/Low が `p_liq` に触れたらその時点で清算、エクイティから残り IM を全没収

### 5. ファンディング

Perp の funding はあらかじめ実データから読む。8時間ごとに:

```
fund_payment = pos * mark_price_at_funding * funding_rate
```

long が `funding_rate > 0` なら支払い、`< 0` なら受取。

### 6. 既知の検証シナリオ

| 日付       | イベント                  | 期待挙動                                  |
|-----------|--------------------------|------------------------------------------|
| 2020-03-12 | コロナクラッシュ          | 30%超下落、高レバロングは即清算          |
| 2021-05-19 | BTC -30% フラッシュクラッシュ | ストップが滑り、清算が連鎖             |
| 2022-11-08 | FTX 連鎖                 | 数日にわたるトレンド下落、トレイリングが効く |

各シナリオで「100倍ロング、初期100万」が想定通りに 0 になることを integration test で検証する。

## 自律エージェントのループ

```
while not done:
    hypothesis = agent.next_hypothesis(history)
    code      = agent.implement(hypothesis)
    result    = backtest.run(code, grid)
    insight   = agent.analyze(result)
    history.append((hypothesis, result, insight))
    agent.checkpoint()
```

人間は週に1度、`history` をレビューし方向修正のみ行う。
