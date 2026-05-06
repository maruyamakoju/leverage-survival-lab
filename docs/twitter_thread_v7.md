# Twitter スレ V7 — Stage-Gate / 195 セル全 fail

12 ツイート。日本語・英語の 2 セット。

---

## JP 版

### 1/12

100倍レバの生存率を確かめるプロジェクト3日目、心の片隅に出てきた「いいエッジが出たら
実弾入れたい」を希望的観測でなく数値で詰めるために Stage-Gate というプロトコルを作った。
1日で5ラウンド回した結果、195セル全部 fail だった。記録を残す。🧵

### 2/12

Stage-Gate は 6 段階の関門:
G0: 戦略の経済的成立性 (Sharpe / Risk of Ruin / 年率 log-ret)
G1: BTC/ETH/SOL でロバスト
G2: walk-forward / regime
G3: paper live 30営業日連続
G4: kill switch / 24/7監視
G5: 失っても回る上限額の事前確定 + 30日クーリングオフ

### 3/12

Round 1 (探索): 5戦略 × 75セル × N=200 windows、BTC funding込み。
結果: 0/75 PASS。最良 cell は trend_filtered_sma 1x SL=-5%、年率 +12%、bust 0%。
だが Deflated Sharpe で全滅。Bonferroni n_trials=75 が効きすぎたという設計問題。

### 4/12

Round 2: trend_filtered_sma 単独固定、window {30,90,180}日 × 12セル。
n_trials=12 に下げて評価。結果: 0/36 PASS。
最良 sample Sharpe は +0.64 (90d 1x SL=-2%)。Bonferroni を完全に外した
n_trials=1 でも、Sharpe ~0.6 では実弾運用に必要な水準 (Sharpe>1) には届かない。

### 5/12

「BTC で偶然じゃないか?」を確かめるため Gate 1 preview として ETH/SOL でも評価。
ETH/SOL の funding rate は環境制約で取れず funding なし (preview 限定) だが —
1x SL=-5%: BTC Sharpe +0.57, ETH Sharpe **-0.18**, SOL +0.63
ETH で消える。アセット依存。

### 6/12

「1h 足が悪いだけかも」を消すため日足にリサンプル。
SMA(20,50,200) は標準的なテクニカル設定、window 240/365/540 bars。
結果: 0/36 PASS。最良 Sharpe +0.15 (240d 1x no-SL)。
365d 5x no-SL で平均 -2074% (完全破綻)。timeframe を変えても消えない。

### 7/12

SMA系を諦めて Round 3: FundingFlipStrategy へ。
「funding 過熱側が支払う」mean-reversion 仮説、external signal でテクニカルとは別物。
結果: 0/12 PASS。ただし median trades = 1 / 90日。
threshold=0.0003 が高すぎて signal がほぼ立たない。事実上機能不全。

### 8/12

5ラウンド集計:
Round 1: 0/75
Round 2: 0/36
Gate 1 preview: 0/36
Timeframe round: 0/36
Round 3: 0/12
合計: 0/195 PASS

現リポジトリの 6 戦略では Gate 0 を通せる戦略は存在しない。

### 9/12

教訓:
1. Sharpe 0.5 程度では cost (手数料 + funding + slippage) に飲まれる
2. Bonferroni / DSR / window-length / n_trials は絡み合う。設計時に通せない構造を作りうる
3. BTC のエッジが ETH に転送されない。アセット特性は無視できない
4. SMA系は bull後追い、bear/横ばいで cost を吐く
5. external-signal 戦略は threshold 設計が neat に効く

### 10/12

これらは戦略のチューニング不足ではなく構造的観察。
僕は実弾を入れたかったが、今日のデータは「現戦略では入れる根拠なし」を強く支持する。
CLAUDE.md「実弾0円」ルールは前より強い根拠で支えられている。

### 11/12

撤回するなら、これらのデータが覆る別の証拠を持ってきて、明示コミットで残すこと。
ふんわり「いずれは…」では撤回しない。これも自分との約束。
否定的結果も等しく公開、は最初から pre-register したルール。今日それを履行している。

### 12/12

Repo: github.com/maruyamakoju/leverage-survival-lab
詳細記事 (note/zenn): docs/blog_draft_v7_stage_gate.md
Stage-Gate 仕様: docs/stage_gate.md
進捗 snapshot: docs/stage_gate_status.md

希望的観測でなく数値で詰めるとどうなるか、の 1 日記録でした。

---

## EN 版

### 1/12

Day 3 of my 100x-leverage survival study. To stop "what if I quietly
slip in real money once an edge shows up" from running my brain, I
wrote a Stage-Gate protocol and ran 5 rounds in one day. Result:
0 / 195 cells pass. Thread.

### 2/12

Stage-Gate is 6 gates:
G0 — strategy economic viability (Sharpe / Risk of Ruin / annual log-ret)
G1 — robust across BTC/ETH/SOL
G2 — walk-forward / regimes
G3 — paper-live 30 trading days
G4 — kill switch / 24-7 monitoring
G5 — pre-commit a "loss I can absorb" cap + 30-day cooling off

### 3/12

Round 1 (exploration): 5 strategies × 75 cells × N=200 windows, BTC,
funding included. 0/75 pass. Best cell is trend_filtered_sma 1x SL=-5%
with +12% annualised return and 0% bust. But all cells lose on the
Deflated Sharpe — Bonferroni n_trials=75 was too punishing.

### 4/12

Round 2: lock strategy to trend_filtered_sma, evaluate window
{30,90,180}d × 12 cells. Bonferroni drops to n_trials=12. Result:
0/36 pass. Best sample sharpe is +0.64. Even at n_trials=1 (no
correction), sharpe ~0.6 is far from the >1 needed for real trading.

### 5/12

To rule out BTC luck I ran a Gate 1 preview on ETH/SOL. Funding
rates were unreachable from this env, so it's preview only.
At 1x SL=-5%:
BTC sharpe +0.57, ETH sharpe **-0.18**, SOL +0.63.
The edge does not transfer to ETH. Asset-conditional.

### 6/12

To rule out "1h is just bad", resample to daily. SMA(20,50,200) at
windows 240/365/540 bars. Result: 0/36. Best sharpe +0.15. At 365d
with 5x no-SL the strategy averages -2074% (complete wipeout).
Changing timeframe does not save it.

### 7/12

Round 3: switch family. FundingFlipStrategy — "the overheated side
pays funding so extreme funding mean-reverts". External signal,
not technical. Result: 0/12. But median trades = 1 per 90d window;
threshold=0.0003 is in the tail of actual funding distribution, so
the signal almost never fires. Effectively broken.

### 8/12

Round tally:
R1 0/75, R2 0/36, G1 preview 0/36, timeframe 0/36, R3 0/12.
Total: 0 / 195 cells pass.

No strategy in the current repo passes Gate 0 on cost-aware backtests.

### 9/12

Lessons:
1. Sharpe ~0.5 is eaten by cost (fees + funding + slippage).
2. Bonferroni / DSR / window-length / n_trials interact; you can
   build a design that's unpassable before strategies are even run.
3. BTC edges don't transfer to ETH. Asset properties matter.
4. SMA family chases bulls and bleeds in bear/chop.
5. External-signal strategies hinge on threshold design.

### 10/12

These are structural observations, not tuning failures.
I wanted real-money mode. Today's data argues strongly against it.
The "0 yen real money" rule in CLAUDE.md now stands on stronger
evidence than it did yesterday.

### 11/12

Reversing it would require evidence that overturns this, in an
explicit commit. Not a chat-time vibe shift. Publishing negative
results equally to positive ones was pre-registered on day 0;
today executes that.

### 12/12

Repo: github.com/maruyamakoju/leverage-survival-lab
Long write-up: docs/blog_draft_v7_stage_gate.md
Protocol: docs/stage_gate.md
Snapshot: docs/stage_gate_status.md

What "datapoint-driven instead of vibe-driven" looks like, in one day.
