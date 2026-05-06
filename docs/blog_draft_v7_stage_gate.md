# Stage-Gate を通したら、5 ラウンド 195 セル全部 fail だった話

> 100倍レバの生存率を確かめにいったら、結局のところ「低レバですら勝てない」という話に
> 行き着いた。実弾を入れたかった自分が、実弾を入れない結論を自分のデータで突きつけられた、
> 1 日の記録。

## なぜこんな話を書くか

僕は 24 歳のフリーランスエンジニアで、2026 年 5 月から「Leverage Survival Lab」という
8 週間のクオンツ実証プロジェクトをやっている。目的は 3 つ:

1. 100 倍レバの生存率を実データで定量化する (pre-registration 済の H1〜H4 仮説)
2. Claude Code に 1 週間連続自律実行させるリファレンス実装をつくる
3. 上記 2 つを公開して AI×クオンツ領域での個人ブランディングを進める

実弾は 1 円も入れない、を最初から `CLAUDE.md` に書いた。だが正直なところ、
心の片隅では「いいエッジが見つかったらこっそり実弾を入れたい」という気持ちがあった。

その気持ちが顔を出したので、希望的観測ではなく数値で詰める仕組み、**Stage-Gate** を
作って 1 日で殴り込みをかけた。結果は 5 ラウンド × 195 セル全部 fail。
本記事はその顛末。

## Stage-Gate とは何か

「もし実弾を入れるとしたら、何が揃えば『行ける』と言えるか」を pre-register したもの。
6 段階の関門:

- **Gate 0** — 戦略の経済的成立性: median 年率 log-return > 0、Deflated Sharpe > 0.95、
  Risk of Ruin (250d, equity<50%) < 5%
- **Gate 1** — Cross-asset robustness: 同じパラメータで BTC/ETH/SOL すべて Gate 0
- **Gate 2** — Walk-forward / regime: 12 期 walk-forward、最悪期 Sharpe > -0.5、既知クラッシュで
  口座 ≥ 50%
- **Gate 3** — Paper live で 30 営業日連続再現
- **Gate 4** — 24/7 モニタリング、kill switch、税務帳簿の整備
- **Gate 5** — 「失っても生活が回る上限額」を事前確定、30 日のクーリングオフ

ルール:

- 全ゲート通過まで実弾は1円も入れない
- 通った後も `CLAUDE.md` 「実弾0円」を撤回する明示コミットを別途打つまで実弾不可
- 数値基準を後から緩めるのは pre-registration 違反
- 通らなかった事実も等しく公開する

## 入力データ

- BTC/USDT 1h, 6 年強 (2020-01-01 〜 2026-05-05、55,594 bars)
- ETH/USDT 1h, 6 年強
- SOL/USDT 1h, 5.7 年
- BTC funding rate (8h 刻み, 4,171 ticks)
- 戦略 6 種: random, sma_cross, rsi, bollinger, breakout, trend_filtered_sma, funding_flip

コストモデル: taker 0.04% + 片道 0.05% slippage + 実 BTC funding rate (8h 単位で適用)。
これは Binance USDT-M Perp VIP0 を参考にした保守的な設定。

## Round 1: 5 戦略 × 75 セル × N=200 → 0/75 PASS

最初の Gate 0 評価は探索的に: 5 戦略 (random を除く) × 5 lev × 3 SL × 1 TP = 75 セル。
各 N=200 ランダム 30 日窓。BTC、funding 込み。

結果は **全セル fail**。だが内訳に意味があった。

DSR 抜きの 2 条件 (median return + bust rate) はパスする 5 セルがあった。最強は
`trend_filtered_sma 1x SL=-5%`: 年率 +12.1%、30 日 bust 率 0.0%。

ところが Deflated Sharpe Ratio (DSR) が全セルで prob ≈ 0。理由を追ったら、
これが**戦略の問題ではなく Gate 0 のサンプル設計の構造的問題**だった:

- n_trials = 75 で Bonferroni 補正すると、DSR > 0.95 を通すには Sample Sharpe > 約 2.4 必要
- 30 日 single window の sample Sharpe は構造的に低い (window 内 PnL volatility が大きい)
- 結果、どの戦略でも Sharpe 2.4 に届かない

これは僕の Gate 0 設計のミスだ。後で緩めると pre-reg 違反だが、別 round として
切り直すのは OK。

## Round 2: trend_filtered_sma 単独 × 3 windows → 0/36 PASS

戦略を `trend_filtered_sma` (= bot V3.9 で実装した SMA(20/50/200) クロス + 200日 SMA フィルタ)
1 個に固定。Bonferroni n_trials を 75 → 12 (lev × SL) に下げる。さらに window を
30/90/180 日の 3 段階で見る。

|  | 30d | 90d | 180d |
|---|---:|---:|---:|
| Top median ann log-ret | +26.7% | +102.7% | +15.5% |
| Top sample Sharpe | -0.08 | -0.85 | +0.20 |
| 全 PASS 数 | 0/12 | 0/12 | 0/12 |

window を伸ばしても **Sample Sharpe は最良で +0.64** (90d, 1x SL=-2%)。
Bonferroni を完全に外して n_trials=1 にしても、年率 Sharpe ~0.6 ではちゃんとした
エッジとは呼べない。**実弾運用に必要な Sharpe > 1 (after-cost) には全く届かない**。

これは Bonferroni でも window でもなく、戦略のエッジが本質的に弱いという結論。

## Gate 1 preview: 1x SL=-5% を BTC/ETH/SOL で並べる

ETH/SOL の funding rate を ccxt で取りに行ったが sandbox 環境で network unreachable。
funding なしの preview として cross-asset を見た。

| Asset | 1x SL=-5% Median ann log-ret | Sample Sharpe | 90d bust |
|---|---:|---:|---:|
| BTC (funding 込み) | +19.15% | **+0.57** | 0.00% |
| ETH (funding なし) | +16.32% | **-0.18** | 6.50% |
| SOL (funding なし) | +60.14% | **+0.63** | 13.57% |

ETH で Sharpe がマイナスに沈む。**戦略は「BTC で偶然」というより「ETH では成立しない」。**
Gate 1 が要求する「同パラメータで複数アセットすべて robust」を、preview の段階で既に満たさない。

ETH で Sharpe が落ちる理由は仮説段階だが、ETH の方が BTC よりも複雑なオルトコイン的な
価格挙動 (DeFi イベント連動、L2 ローンチ、ETF 期待など) を含み、純粋なテクニカル
trend-follower のエッジが薄まると考えている。検証はこの記事の範囲外。

## Timeframe round: daily でもダメ

「1h が悪いだけかも」を消すために 1h を daily に resample。SMA(20, 50, 200) は
daily だと 20日/50日/200日 = 標準的なテクニカル設定になる。window 240/365/540 bars
(= 8ヶ月/1年/1.5年) で 200 SMA の warmup を満たしつつ意味あるサンプルを取る。

| window | Top median ann log-ret | Top Sharpe | Top bust |
|---|---:|---:|---:|
| 240d | +2.42% | +0.15 | 1.05% |
| 365d | +2.11% | +0.06 | 12.63% |
| 540d | +31.00% | -0.59 | 58.55% |

daily でも Sharpe は +0.15 が最良。 365d 5x no SL で平均 -2074% (完全破綻)。
1h でも 1d でも、SMA family のエッジは cost に飲まれる。

## Round 3: 戦略族を Funding 系に切り替え

SMA 系を諦めて FundingFlipStrategy へ。「funding rate が極端に正なら過熱したロングが
支払う構造なのでショート、極端に負ならロング」という mean-reversion 仮説。
external signal なのでテクニカル指標とは性格が違う。

threshold = 0.0003 (年率約 33% 相当 funding) は実装当時のクラスデフォルト値で、これを
そのまま pre-register。

結果: **0/12 PASS**。ただし観察として **median trades = 1 / 90d window**。

threshold = 0.0003 は Binance BTC funding の実分布の極端側で、90 日間でほぼ発火しない。
事実上「戦略が機能していない」状態だが、これも pre-reg 通り保持。後付けで threshold を
0.0001 などに下げるのは Round 4 で別 pre-reg を切る話。

## 5 ラウンドの集計

| Round | 対象 | PASS / 評価 cells |
|---|---|---:|
| Round 1 | 5 strategies, BTC 1h, funding 込み | 0 / 75 |
| Round 2 | trend_filtered_sma × 3 windows | 0 / 36 |
| Gate 1 preview | trend_filtered_sma cross-asset | 0 / 36 |
| Timeframe round | trend_filtered_sma daily | 0 / 36 |
| Round 3 | FundingFlip 90d | 0 / 12 |
| **合計** | | **0 / 195** |

## 何が分かったか

1. **エッジが「ほぼある」程度では cost に勝てない**。Sharpe 0.5 程度の戦略は手数料 + funding +
   slippage で削られて、ピリオドあたりの期待値が回収できない
2. **Bonferroni / DSR の使い方は設計依存**。n_trials × n_periods × window-length が
   絡みあって、戦略を選ぶ前から「設計上ほぼ通せない」状況をつくる可能性がある。
   Round 1 の DSR 全 0 はその証拠
3. **BTC で出たエッジは ETH に転送されない**ことが多い。アセット依存の構造的特性
   (流動性、ボラ、相関、イベント駆動)を無視できない
4. **SMA + 長期トレンドフィルタは bull market 後追いになる**。戦略が成立する局面が
   事前に決まっており、bear や横ばいで cost を吐き続ける
5. **funding 系戦略は threshold 設計に neat に依存**する。実分布を見ずにクラスデフォルト
   をそのまま使うと発火しないので、実装と pre-reg は別作業

## 自分にとっての含意

僕は実弾を入れたかった。だが今日 1 日で集めたエビデンスは「現リポジトリの戦略で実弾を
入れる根拠は無い」ことを 5 ラウンド分の数値で支持している。

`CLAUDE.md`「実弾0円」ルールは今日の前より強い根拠で支えられている。
ルールを撤回するなら、これらのデータが覆る別の証拠を持ってきて、明示コミットで残すこと。

ふんわりした「いずれは…」では撤回しない。これも自分との約束。

## これからどうするか

続編候補:

- **Round 4**: FundingFlip の threshold を {0.0001, 0.0002} に下げて再評価 (新 pre-reg)。
  さらに ボラ breakout / オーダーフロー系の戦略を追加
- **アセット拡大**: ETH/SOL の funding rate 取得 (環境が整い次第) → Gate 1 公式評価
- **時間軸の刷新**: tick / 数分足 の microstructure 寄り戦略
- **撤退**: 「現戦略では爆稼ぎ不可能」を H1〜H4 の知見と合わせて公開して 8 週終了

どれを選んでも、Stage-Gate プロトコル自体は今後の自分への遺産として残せる。
誰でも公開リポジトリで再現できる。

## リポジトリと再現

- GitHub: `maruyamakoju/leverage-survival-lab`
- 実行コマンド (5 ラウンド再現):
  ```
  python scripts/gate0_eval.py --n-windows 200          # Round 1
  python scripts/gate0_round2.py --n-windows 200        # Round 2 (3 windows)
  python scripts/gate1_preview.py --n-windows 200       # Gate 1 preview
  python scripts/gate0_round2_daily.py --n-windows 200  # Timeframe round
  python scripts/gate0_round3.py --n-windows 200        # Round 3
  ```
- 結果 parquet と markdown は `results/gate0_*.parquet` と `results/gate0_*_report.md`
- Stage-Gate 仕様: `docs/stage_gate.md`、進捗 snapshot: `docs/stage_gate_status.md`

## おしまい

「爆稼ぎしたい」を、希望的観測でなく数値で詰めると、こうなる。
Round 4 で何か出るかもしれないし、出ないかもしれない。
出ても出なくても、Stage-Gate を通すというプロトコルだけは残る。

— maruyama (2026-05-07)
