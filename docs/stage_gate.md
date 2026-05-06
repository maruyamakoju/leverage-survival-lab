# Stage-Gate — 実弾投入までの関門

このドキュメントは、Leverage Survival Lab のシミュレーション/ペーパー結果から
**いつか実弾(現金)取引に移行する判断**を希望的観測ではなく数値基準で行うためのプロトコルである。

## 上位ルール

1. **全ゲートを順番に通過しない限り実弾は1円も入れない**。
   先送り・後出し・順番入れ替えは [pre-registration](hypotheses.md) 違反として扱う。
2. **`CLAUDE.md` 冒頭の「実弾0円」ルールが現時点で生きている**。
   仮に Gate 5 まで全通過しても、実弾投入の前にこのルールを撤回する明示コミットを別途打つこと。
   その場の会話・気分・期待利益では撤回しない。
3. **各ゲートは pre-register された数値基準で判定する**。基準を後から緩める変更は、
   別コミットで「なぜ緩めたか」を残し、過去ログを破棄しない。
4. **どのゲートも通らなかった結果も等しく公開する**。
   「行けない」と分かることもこのプロジェクトの正規の成果。
5. **戦略は事前に1個固定する**。N 個試して最良を拾う行為は multiple testing 違反。
   複数試したい場合は Bonferroni / FDR で補正した閾値を使う。

---

## Gate 0 — 戦略の経済的成立性 (cost-aware backtest)

> 「コスト込みで期待値プラスか」。これが No なら以降全部無意味。

**入力データ**: BTC/USDT 1h, 6+ 年, N≥500 ランダム30日窓 (シード固定)。

**コストモデル必須項目**:
- Taker 手数料 (Binance Futures 既定 0.05% / 取引)
- スプレッド (1h 足 mid を使う場合は片道 1bp 程度を最低でも乗せる)
- ファンディング (8h 毎、過去実測 funding rate を再現)
- 清算ペナルティ (Isolated 清算時 maintenance margin 喪失)

**合格基準** (すべて満たす):
| 指標 | 閾値 |
|---|---|
| Median annualized log-return (after costs) | > 0 |
| Deflated Sharpe (Bonferroni 補正) | > 1.0 |
| Risk of Ruin (250営業日, 残高 < 50% に到達する確率) | < 5% |
| 戦略は事前固定 | 1 戦略のみ、param sweep 後の最良値を拾わない |

**現状**: H3 結果より「1x ですら全戦略が手数料負け」。
Gate 0 を通る戦略の探索が**プロジェクトの最初のボス**であり、これが見つからない場合は
「100倍レバ含め全レバ帯で爆稼ぎは不可能」を pre-registered 通り公表して終わる。

### Round 1 (2026-05-07) で判明した DSR 設計上の構造的問題

第1回評価 (`scripts/gate0_eval.py`、N=200、75 cells) で全 cells の Deflated Sharpe Ratio が
prob ≈ 0 で fail した。原因は **30日 single window の cross-sectional sample で算出する
Sharpe が性質上低くなる** ことと、**75 cells の Bonferroni 補正で DSR 閾値が ~ Sharpe 2.4 に
跳ね上がる** こと。

この設計だと、たとえ年率 +20% を出す戦略でも DSR では叩き落とされる。
本来 DSR は「多重試行で偶然得られた高 Sharpe を割り引く」ためのものだが、cell ごとの
Sharpe 自体が 30d window では上がりにくく、構造的に通せない設計になっていた。

**改訂案 (まだ採用していない)**:
- 戦略を事前に 1 個固定して n_trials=1 で評価する round を別 pre-reg で切る
- window を 90d / 180d に伸ばして Sharpe を引き出しやすくする
- メタクライテリアの順序を変える (median return + bust rate を first gate、DSR は最後)

これらの改訂は別コミットで「なぜ妥当か」を残すこと。
**Round 1 の「全 fail」結果自体は pre-reg どおり保持する** (緩めた基準で再評価して書き換えない)。
詳細は [stage_gate_status.md](stage_gate_status.md) の Round 1 結果を参照。

### Round 2 仕様 (pre-registered, 2026-05-07)

Round 1 の DSR 構造的問題への対応として、以下の改訂を **別 round として** 実行する。
Round 1 の判定 (0/75 PASS) は変更しない。

**Round 2 の選択候補からの戦略事前固定**:
- 戦略 = `trend_filtered_sma` (= bot V3.9 `trend_sma` と同一ロジック) **単独固定**
- 理由: Round 1 の "DSR 抜き 2 条件パス cells" の 5 件中 3 件を占めて支配的だったため。
  また cross-asset (Gate 1) preview に進む際、複数戦略を同時に試すと Bonferroni が再爆発する
- これは Round 1 結果から戦略を1個拾った行為であり、その意味で
  **Round 1 が探索フェーズ、Round 2 以降が confirmation フェーズ** という二段階設計に切り替える宣言

**サンプル設計**:
- window_days = **{30, 90, 180}** の 3 段階を独立に評価する
  (Sharpe の window 期間依存性を可視化するため)
- N = 200 ランダム窓 / 各 window-length / seed = 20260507
- レバレッジ = {1, 2, 3, 5}x (10x 以上は Round 1 で全戦略爆損が確認済のため除外)
- SL = {None, -0.02, -0.05}
- TP = {None}
- 実 Binance funding 注入 (BTC は確定、ETH/SOL は取得後)

**判定**:
- 戦略は事前 1 個固定なので **n_trials = レバ × SL = 12** で Bonferroni 適用 (戦略選択の補正は不要)
- Gate 0 の 3 条件はそのまま:
  - median_annual_log_return > 0
  - deflated_sharpe_prob > 0.95 (n_trials=12 で補正)
  - bust_rate_window_50pct < 5%
- 3 つの window-length それぞれで判定し、**いずれか1つで合格すれば Gate 0 暫定通過**として
  Gate 1 (cross-asset) に進む。3 つすべてで合格しなければ「期間に依存して通る/通らない」を
  追加観察として記録する

**改訂理由 (なぜ Round 1 を踏襲しないか)**:
1. Round 1 の n_trials=75 (5 戦略 × 5 lev × 3 SL) は、戦略を選ぶ前のスクリーニング段階で
   Bonferroni を効かせていた。これは「戦略選択の偽陽性回避」としては正しい
2. Round 2 では戦略を pre-register で1個固定することにより、戦略選択の自由度を消去。
   残るのはレバ×SL の感度マップで、これは同戦略のチューニング感度であり、
   n_trials=12 のままでも Bonferroni 効果は弱まる
3. window_days を伸ばすことで sample Sharpe が引き出しやすくなる (時間方向の集約)
4. Round 1 の cell-level 判定は維持。Round 2 で通った戦略は Gate 1 (cross-asset) で再現性確認

### Round 3 仕様 (pre-registered, 2026-05-07 夜)

Round 1 + Round 2 + Gate 1 preview + timeframe round の 4 結果すべてで
trend_filtered_sma 系 (= テクニカル SMA ファミリー) が Gate 0 を通せないことが確定。
これは戦略のチューニング不足ではなく、SMA family のエッジ自体が cost 込みでは
存続しないという結論。

そこで Round 3 では **戦略ファミリーを刷新** する:

**戦略の事前固定**:
- 戦略 = `FundingFlipStrategy` (`src/leverage_survival_lab/strategies/funding_filter.py`)
- パラメータ事前固定: `threshold=0.0003` (~年率33% funding), `lookback=24` (24h 移動平均)
- 戦略選択の理由 (pre-reg として残す):
  1. **エッジの源泉がテクニカル指標ではない**: funding rate は perpetual swap の
     需給メカニズムで「過熱した側が支払う」構造のため、構造的な mean-reversion 圧力を持つ
  2. SMA family が完全に fail した今、external signal (funding) ベースの戦略を試す価値が高い
  3. funding_filter.py は実装済みで、Round 1 のグリッドには組み込まれていなかった (Round 1 結果に未測定)

**サンプル設計**:
- window_days = **90** (Round 2 のスイートスポット、SMA フィルタの warmup 制約も無いので 30d に短縮しない)
- N = 200 ランダム窓 / seed = 20260507
- レバレッジ = {1, 2, 3, 5}x
- SL = {None, -0.02, -0.05}
- TP = {None}
- 実 Binance BTC funding 注入 (バックテスト側 cost) + funding signal source 同 series
- n_trials = 12 (lev × SL, 戦略は事前固定)

**判定基準**:
- Gate 0 三条件 (median ann log-ret > 0 / DSR > 0.95 / bust < 5%) はそのまま
- Round 3 で通った場合、Gate 1 (cross-asset) に進む
- 通らなかった場合、SMA family + Funding family が両方 fail したことを根拠に
  「現リポジトリの戦略では実弾投入の根拠なし」を最終結論として公開する

**改訂理由補足**:
- Round 3 は Round 2 と独立に評価する (戦略族が違うので Bonferroni は分離)
- Round 2 の結果は変更しない
- "Round 1 で 6 戦略中 funding_flip だけ評価しなかった" 件は、当時 grid runner が
  funding_series を strategy に注入する経路を持っていなかった技術的制約による。
  Round 3 ではこの制約を script 側で解消する (grid.py を変えず、Round 3 専用スクリプトで
  BacktestConfig + run_backtest を直接呼ぶ)

---

## Gate 1 — Cross-asset robustness

> 「BTC の 1 アセット偶然」を排除する。

**入力**: BTC, ETH, SOL の 1h データ各 6+ 年。

**合格基準**:
- 3 アセットすべてで **同一パラメータ**で Gate 0 を独立に満たす
- 各アセットの IS Sharpe / OOS Sharpe 比 > 0.5 (過学習でない)
- アセット別にパラメータをチューニングする行為は禁止

**現状**: `scripts/codex_lowlev_cross_asset.py` がこのゲートの検証ツール (未実行)。
1〜10x 帯で sma_cross / rsi / breakout / trend_filtered_sma を sweep する設計。

---

## Gate 2 — Walk-forward & regime robustness

> 過去レジームのチェリーピックでないか。

**合格基準**:
- 12 期 walk-forward、各期の Sharpe (after-cost) 中央値 > 0、最悪期 > -0.5
- 既知クラッシュで口座 ≥ 50% 維持:
  - 2020-03-12 コロナクラッシュ
  - 2021-05-19 BTC -30% 1日
  - 2022-11-08 FTX 崩壊
- 高ボラ regime (実現ボラ上位 25%) と低ボラ regime (下位 25%) の両方で Sharpe > 0

---

## Gate 3 — Paper live で 30 営業日連続再現

> 実装バグ / 約定 slippage / 接続断 / 微妙な実装ズレが顕在化する場所。

**合格基準**:
- ペーパー口座で 30 営業日連続稼働。手動再起動・bug fix なし
  - heartbeat 切断はカウンタリセットの理由にしない (再起動を要するならそれは再 1 日目)
- 実約定 vs バックテスト想定の median slippage < 0.05% / 取引
- 月次実 PnL が、バックテスト予測 PnL 分布の 25-75 percentile に収まる
- DECIDE_ERROR / position 同期ズレ等のシステム異常 = 0 件

---

## Gate 4 — オペレーション準備

> 事故率の支配項はだいたいここ。コードでなく運用。

**合格基準**:
- 24/7 モニタリング:
  - 価格 stale alert (≥ 60s 価格更新なし)
  - PnL alert (-X% / 1h, -Y% / 24h)
  - kill switch (1 コマンドで全ポジ手仕舞い + bot 停止)
- 障害 runbook を文書化 (取引所 API 停止 / API キー漏洩 / bot 暴走 / マシン死亡)
- 取引所 API の rate limit / 障害時の挙動を実証 (テストネットで強制再現)
- 税務・帳簿・通貨換算の処理が決まっている (年次申告に耐える形式)

---

## Gate 5 — 財務・心理ゲート (人間の側)

> 数値で殴れない部分。事前に紙に書いて固定する。**この紙は後で書き直さない**。

**合格基準**:
- "失っても生活が回る" 上限額 X 円を事前確定して別ファイルにコミット
- 月次ドローダウン -30% を 1 か月見続けても損切ルールを守ると誓約 (本人の署名つき記録)
- Gate 4 完了後 **30 日のクーリングオフ期間**。気が変わらなかったら次へ
- 開始額は X の 1/10 以下、3 ヶ月後に再評価して初めて X に近づける
- 借入金・生活費・課税待ち資金は対象外

---

## ゲート未達時の振る舞い

- どのゲートで停止しても、**止まったこと自体を成果として公開する**。
- "戦略を別のに変える" "アセットを増やす" 等の改修は、**新しい pre-registration を切って Gate 0 から再開**する。
  既存ゲートの結果を保持したまま戦略だけ差し替える行為は禁止。
- Gate 5 で「人間の側が無理」と判断した場合、それも正規の停止理由。
  「機械的には通ったから入れる」ではなく、「人間が無理と思ったら入れない」を上位ルールにする。

---

## 改訂ルール

このドキュメントの数値基準・順序・運用ルールを変更する場合:
- 単独コミットで変更し、**変更理由をコミットメッセージに残す**
- 既に進行中のゲート評価には新基準を遡及適用しない (適用するならゲート評価をやり直す)
- 基準を緩める変更には「なぜ緩めても妥当か」の根拠を本文に追記する。
  根拠なしの緩和は本プロジェクトの自殺行為。
