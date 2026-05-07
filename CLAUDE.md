# CLAUDE.md — Leverage Survival Lab 用ガイダンス

このファイルは Claude Code が本リポジトリで作業するときに参照する内部ガイドです。

## プロジェクトの本質

100倍レバの生存率を統計的に検証する**実証研究プロジェクト**。エンジニアリング+クオンツ+発信の三位一体。

## 絶対に守ること

1. **実弾(現金)は1円も投入しない** — すべて自前シミュレータで完結。
   実弾投入の議論が出たら必ず [docs/stage_gate.md](docs/stage_gate.md) (Stage-Gate プロトコル)
   と [docs/stage_gate_status.md](docs/stage_gate_status.md) (進捗 snapshot) を参照。
   現状 6 ラウンド 0/219 PASS で実弾投入は数値的に正当化されない
2. **プレ・レジストレーション済の4仮説を改竄しない** — `docs/hypotheses.md` を後から都合よく書き換えない。
   Stage-Gate の各 Round (R1, R2, R3, R4) も同様に pre-reg 済、結果は事後修正禁止
3. **バイアス対策を妥協しない**:
   - look-ahead: バー終値で判断→次バー始値で約定
   - survivorship: 上場廃止銘柄も含める(暗号は影響限定)
   - multiple testing: Deflated Sharpe / Bonferroni / FDR
   - walk-forward: in-sample/out-of-sample 厳格分離
4. **否定的結果も等しく公開する** — 「100倍レバは勝てない」が出たらそのまま出す。
   Stage-Gate 6 ラウンド全 fail もそのまま `docs/blog_draft_v7_stage_gate.md` で公開
5. **再現可能性** — Notebook/CLIから誰もが結果を再現できること

## 開発上の原則

- レバレッジ清算・手数料・ファンディングは **自前で厳密実装**(vectorbtの既定では不十分)
- 既知の歴史的シナリオ(2021/05/19 BTCクラッシュ, 2022/11/08 FTX, 2020/03/12 コロナ)で再現性検証
- 重い実験は `data/processed/` から Parquet で読み、結果は `results/` に Parquet で出す
- すべての実験は `(commit_hash, params, seed)` で再現可能に

## ディレクトリと責務

| Path                              | 責務                                       |
|-----------------------------------|-------------------------------------------|
| `src/leverage_survival_lab/data/` | ccxt経由データ取得、Parquet I/O           |
| `.../engine/`                     | 証拠金・清算・手数料・ファンディングモデル |
| `.../strategies/`                 | 7戦略の Signal 生成 (random/sma/rsi/bollinger/breakout/trend_filtered_sma/funding_flip) |
| `.../backtest/`                   | vectorbt連携、実験ハーネス、グリッド実行 (funding 注入対応済) |
| `.../analysis/`                   | 統計検定、可視化、Risk of Ruin            |
| `.../agent/`                      | Claude Code 自律実行のフック              |
| `.../trading/`                    | bot (V3.x シリーズ、ペーパー口座、live demo) |
| `tests/unit/`                     | pytest単体(高速、CIで毎回実行)         |
| `tests/integration/`              | 結合テスト(slow markerでオプトイン)    |
| `scripts/gate0_*.py`              | Stage-Gate Round 1-4 評価スクリプト       |
| `scripts/gate1_preview.py`        | Cross-asset preview (Gate 1)              |
| `scripts/make_v7_figures.py`      | 公開用図表生成                            |

## コーディング規約

- Python 3.11+。型注釈は **必須**(mypy strict)
- 公開関数は docstring 必須
- データ構造は **pandas DataFrame** または **dataclass / pydantic** を使う(dictの生流通禁止)
- 価格・PnL等の数値は **float64**(decimalは速度面で不採用、誤差は適切に丸める)
- 乱数は `numpy.random.default_rng(seed)`(レガシーAPI禁止)

## テスト方針

- レバレッジエンジンは **シナリオベースのプロパティテスト** を厚く書く
- 既知の清算価格(Cross/Isolated)、既知の手数料計算を docstring 内 doctest+pytest で検証
- バックテスト全体の回帰は固定 seed のスナップショット(`tests/integration/`)
