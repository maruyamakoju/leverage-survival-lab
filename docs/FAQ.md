# FAQ — Leverage Survival Lab

> 想定される SNS / Issue のツッコミに先回りして答えるドキュメント。

---

## 結果系

### Q. 100倍レバの30日生存率が0%って、信じられないんですけど

各 (戦略, 損切水準) セルで N=数千〜1万のサンプルで 0%、Wilson 95% CI の上限が 0.27%。
直感に反するかもしれませんが、内訳は単純で:

- 100倍レバは 0.5% の逆行で清算
- BTC の 1 時間足ボラは 0.5〜2% が普通(年次換算 50〜100%)
- 30 日 × 24 = 720 時間内に 0.5% を超える adverse move は何度も起きる
- ランダムエントリーでは長期的に半分は loss → 高頻度 + タイトな清算閾値で全滅

数学的には Risk of Ruin = 1 が漸近的に保証される領域。

### Q. クラッシュ期(2020/3、2021/5、2022/11)を意図的に避ければ違う結果じゃない?

避けても駄目です。レジーム別実験 (`scripts/run_regime_experiment.py`) で:
- trend_up: 100x = 0% 生存
- range: 100x = 0% 生存
- crash: 100x = 0% 生存

トレンド期(上昇)でも、ランダムにエントリーする限り short も混ざるし、long でも短期 retracement で清算される。

### Q. ナイーブ戦略しか試してないのが問題では?

確かにそうです。そのため `trend_filtered_sma`(200-SMA トレンドフィルタ付き SMA cross)
を追加して試したところ、レバ 1x〜3x で **正の平均 log-return** を確認(エッジ有り)。
ただし、その戦略でも 25倍以上のレバでは 30日生存率 0% です。
**戦略のエッジは存在しても、高レバで生存できるとは限らない。**

### Q. ポジションサイズを小さくすれば 100倍 OK では?

これも検証済 (`scripts/run_risk_fraction_experiment.py`):
risk_fraction を 1.0 → 0.05 まで下げても、100倍生存率は 0%。
理由: 30日 × 5%/bar の頻度で約 70 回エントリー。各回 0.5% 逆行で清算。
1回の損失は IM(=口座の 5%)に限定されても、累積で枯渇します。

---

## 方法論系

### Q. 手数料が片道 0.04% × taker は高すぎでは?

Binance USDT-M Perp の VIP0 デフォルトに合わせています。VIP9 で 0.017% まで下がりますが、
取引量を確保できる個人は限定的です。
仮に手数料が半分でも、結論はほぼ変わりません(エッジ消失閾値が少し上にずれるだけ)。

### Q. スリッページのモデルが甘くないですか?

`FeeModel`: 片道 0.05%、ストップ約定時は追加 +0.05%。流動性の薄い相場では
これも甘めですが、結論は強化される方向(=セルが緩い結論)。

### Q. look-ahead bias は本当にないですか?

`backtest/runner.py` でシグナルは bar t の close で生成、約定は bar t+1 の **open** で行うことを
エンジンレベルで強制しています。戦略実装者がうっかり違反するパスはありません。

### Q. 多重比較補正は?

H4 の検定で Bonferroni 補正(α/n)を適用済。Deflated Sharpe Ratio
(Bailey & López de Prado, 2014)も `analysis/stats.py` に実装済。

### Q. Walk-forward 検証はしましたか?

`backtest/walkforward.py` + `scripts/walkforward_h3_validation.py` で実装。
`trend_filtered_sma` の OOS log-return は IS と同水準(過学習の兆候なし)。

---

## 実装系

### Q. なぜ vectorbt をそのまま使わない?

レバレッジ清算を厳密にモデル化したかったため。市販ツールはバー終値で
判定するものが多いですが、High/Low に対して判定しないと清算が見落とされます。
`engine/leverage.py` で Isolated / Cross の両方を実装。

### Q. 結果の再現可能性は?

`(commit_hash, params, seed, data_id)` で完全に決定論的。
`scripts/reproduce_all.py` でワンショット再現可能。
`docs/hypotheses.md` のプレ・レジストレーションは git commit hash で
ロック(`4694ff0`、2026-05-05)。

### Q. Windows で時々セグフォルトするのは何?

pandas/numpy のネイティブコードが、長時間プロセスで稀にメモリ違反を出します。
回避策: 大規模実験を `scripts/run_realdata_chunked.py` で 200 windows ずつ
別 subprocess に分割。各 chunk は最大 3 回リトライ。

---

## 投資/法務系

### Q. これは投資助言ですか?

**いいえ**。本リポジトリは観測研究であり、投資助言ではありません。
シミュレーション結果は実取引の成果を保証しません。

### Q. 著者は実際に高レバで取引しましたか?

実弾(現金)は 1 円も投入していません。すべて自前シミュレータ上の実験です。

### Q. 取引所 API の利用規約は?

ccxt 経由の **読み取り専用・低頻度**。各取引所の ToS に従って利用しています。

---

## ロードマップ・拡張系

### Q. ETH/SOL 以外の通貨は?

クロス資産検証は BTC / ETH / SOL の 3 通貨で実施済(全て 100x = 0%)。
Altcoin の特性(より高ボラ、ファンディング不安定)では結論はさらに強化される予測。
PR ウェルカム。

### Q. Cross margin で結果は変わる?

`CrossMarginEngine` を実装済(`engine/cross_margin.py`)ですが、
大規模実験はまだ。Cross は破産までの寿命が短くなる(他ポジションのドローダウンを
くらう)ので、結論は強化される方向と予測。

### Q. 自分でフォークして実験するには?

```bash
git clone https://github.com/maruyamakoju/leverage-survival-lab
cd leverage-survival-lab
pip install -e ".[dev]"
python scripts/reproduce_all.py
```

これで `results/` に図表 + parquet が生成されます。
