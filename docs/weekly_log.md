# Weekly Log

> 各週の進捗・課題・次週の予定を append-only で記録する。Twitter/X で発信する素材としても使う。

## Week 1 — 2026-05-05〜

### 完了

- [x] リポジトリ初期化(git, ディレクトリ構造, README, LICENSE, .gitignore)
- [x] `pyproject.toml`(Python 3.11+, vectorbt/ccxt/numba/scipy 等)
- [x] `CLAUDE.md`(本リポジトリで Claude Code が作業する際の内部ガイド)
- [x] **プレ・レジストレーション** 4 仮説を `docs/hypotheses.md` に固定
- [x] レバレッジエンジン MVP(Isolated, 単一ポジション, 清算/手数料/ファンディング)
- [x] 5戦略のシグナル生成(Random / SMA / RSI / Bollinger / Breakout)
- [x] バックテストランナー(look-ahead 防止、High/Low での清算判定)
- [x] 指標関数(Sharpe / Sortino / Calmar / DD / 生存率 / Risk of Ruin)
- [x] ユニット・結合テスト(pytest)
- [x] 合成データで動くミニ実験スクリプト

### 次週(Week 2)

- [ ] Binance/Bybit から過去 5 年分の OHLCV 取得 → Parquet 化
- [ ] ファンディングレート履歴の取得・整形
- [ ] データ品質検証(欠損・連続異常値・タイムゾーン整合性)
- [ ] 既知シナリオ(2020/03/12, 2021/05/19, 2022/11/08)の DataFrame を切り出して fixtures 化

### 学び・所感

- Look-ahead 防止のため、シグナル → 次バー始値で約定 という制約をランナーの実装レベルで固定した。
  個別戦略実装者がうっかり違反するのを防げる。
- レバレッジエンジンは将来 Cross / 複数ポジション / 部分決済へ拡張するが、
  Week 1 の MVP では Isolated 単一ポジションに絞って完成度を上げた。
- 初期テストで 100x の清算価格期待値を誤記(99.005 と書いた)していたが、
  正しくは 99.5(0.5% 下落で清算)。コードは正しく、テスト/docstring 側を修正した。
  教訓: 数式のセルフチェックは複数の独立な角度で行う。

## Week 2 — 2026-05-05〜(同日進行)

### 完了

- [x] Binance/Bybit 過去 6 年分 OHLCV 取得(ccxt 経由、増分・再開可能)— 55,594 行
- [x] ファンディングレート履歴取得 — 4,171 行
- [x] データ品質検証(欠損 0, 重複 0, 100% complete)
- [x] グリッド実験ランナー(モンテカルロ・並列対応)
- [x] 統計検定モジュール(Wilson CI / 2 比率 z 検定 / Bonferroni / BH-FDR / Deflated Sharpe)
- [x] 自律エージェント骨格(`Hypothesis / Experiment / History`)
- [x] 仮説検定スクリプト(`scripts/test_hypotheses.py`)
- [x] レポート自動生成器(`scripts/generate_report.py`)
- [x] **N=500 実データ実験**(87,325 simulations on real BTC/USDT 6+ years)

### 主要結果(N=500, 実データ Binance BTC/USDT 1h × 6年, 30日窓ランダム抽出)

| 仮説 | 結果 | 主要数値 |
|------|------|---------|
| H1: 100x の30日生存率 < 10% | **強く支持** | 全 25 セルで生存率 0%, **CI 上限 0.76%** |
| H2: 各レバに最適な損切ライン(内点解) | 部分支持 | 5x, 10x の中レバ域で内点解(-1%〜-2%)、それ以外は端点 |
| H3: 戦略エッジ消失閾値 10〜20x | 測定不能 | レバ 1x でも全戦略が負の平均 log-return(手数料負担で edge 消失) |
| H4: 50x 以上で戦略間有意差なし | **支持** | 全比較 p=1.0(全戦略が 0% 生存) |

### 学び

- pandas 3.0 で `pd.DataFrame(list_of_dicts_with_mixed_keys)` がセグフォルトする回帰があった。
  trade レコードのスキーマを統一して回避。
- レバレッジエンジンの清算後 equity を `max(0, ...)` でクランプしないと負の equity が出る(手数料分)。
- 実データ x 50万シミュレーションで H1 の CI 上限が 1% を切る。これは「100倍レバは100% 破産する」と言ってよいレベル。

### 次週(Week 3)

- [ ] Cross margin 対応(現在は Isolated のみ)
- [ ] 部分決済・複数ポジション対応
- [ ] 既知シナリオ(2020/03, 2021/05, 2022/11)での再現性検証
- [ ] Walk-forward 分析の本格実装

## Week 3 — 同日着手

### 完了

- [x] CrossMarginEngine(MVP, 複数ポジション + アカウントレベル清算)
- [x] Walk-forward harness(IS最適化→OOS評価)
- [x] レジーム条件付き実験(trend_up/down/range/crash で個別評価)
- [x] Agent loop 骨格 + 1サイクル demo
- [x] 既知シナリオの結合テスト(LUNA/FTX/COVID/May2021/Bull2021)
- [x] **risk_fraction sweep 実験** — 100x × {1.0, 0.5, 0.25, 0.10, 0.05}, all rf → 生存率0% / CI上限 0.76%
- [x] H1 のレジーム別検証 — trend_up / range / crash で全て 100x 生存率 0%

### 学び

- pandas/numpy 由来のセグフォルトが Windows 環境で間欠発生。回避策:
  1. プロセスごとに小規模分割(rf や regime ごとに別プロセス)
  2. `pd.DataFrame(list_of_dict)` を column-wise builder に置き換え
  3. trade dict のスキーマ統一
- ポジションサイズ縮小は 100倍レバを救えない。30日 × 高頻度エントリで累積損失が IM 制限を超える。
- レジームによらず 100倍は破産する(レジーム依存の希望はない)





H1 と一貫する単調減少が確認できた(本実験の確定はWeek 2以降の実データで再現後):

| Lev  | SL=-0.5% | SL=-1.0% | SL=-2.0% | SL=-5.0% | SL=None |
|------|---------:|---------:|---------:|---------:|--------:|
|  1x  |   100%   |   100%   |   100%   |   100%   |   98%   |
|  2x  |   100%   |   100%   |   100%   |   100%   |   75%   |
|  5x  |   100%   |    95%   |    90%   |    78%   |   37%   |
| 10x  |    74%   |    44%   |    45%   |    10%   |   10%   |
| 25x  |     0%   |     0%   |     0%   |     0%   |    0%   |
| 50x  |     0%   |     0%   |     0%   |     0%   |    0%   |
| 100x |     0%   |     0%   |     0%   |     0%   |    0%   |

※ 合成データ + ランダム戦略 + risk_fraction=1.0 の条件。実データで再現することを Week 5 で確認する。
