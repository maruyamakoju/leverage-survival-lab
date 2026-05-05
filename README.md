# Leverage Survival Lab

> **100倍レバレッジ生存率の実証研究** — Claude Code 自律エージェントによる定量金融バックテスト基盤

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Status: WIP](https://img.shields.io/badge/status-WIP-orange.svg)]()

## 概要

「100倍レバレッジ × 損切ルール」によって個人投資家でも勝てる、という俗説に対する定量的・統計的反証を、再現可能な形で公開する個人プロジェクトです。本リポジトリは以下を目的とします:

1. **Risk of Ruin の定量化** — レバレッジ倍率(2x〜100x)× 損切ライン(-0.5%〜-5%)の格子で生存率をマップ化
2. **Claude Code 自律エージェント** — 1週間連続稼働するバックテスト・リサーチエージェントのリファレンス実装
3. **再現可能性** — モンテカルロ 5万〜20万回シミュレーションを誰もが手元で再現可能に

実弾(現金)は1円も投入しません。すべて自前シミュレータ上の実験です。

## プレ・レジストレーション済 4 仮説

事後の都合の良い結果抽出を防ぐため、実験前に以下4仮説を登録しています([docs/hypotheses.md](docs/hypotheses.md))。

- **H1**: 100倍レバの30日生存率は、いかなる損切ルールでも 10% 未満
- **H2**: 各レバ倍率に最適な損切ライン(タイト過ぎず緩すぎず)が存在
- **H3**: レバ 10〜20倍を超えると取引コスト+ボラドラッグで期待値マイナス
- **H4**: 50倍以上ではナイーブ戦略の生存率がランダム戦略と統計的有意差なし

## アーキテクチャ

```
┌───────────────────────────────────────────────────────────┐
│ L5  Claude Code Agent — 仮説生成→実装→実行→分析の自走     │
├───────────────────────────────────────────────────────────┤
│ L4  Analysis  — Sharpe / DD / Risk of Ruin / 可視化       │
├───────────────────────────────────────────────────────────┤
│ L3  Backtest Runner — vectorbt + 自前拡張                 │
├───────────────────────────────────────────────────────────┤
│ L2  Leverage Engine — 証拠金/清算/手数料/ファンディング     │
├───────────────────────────────────────────────────────────┤
│ L1  Data — Binance/Bybit OHLCV + Funding (Parquet)        │
└───────────────────────────────────────────────────────────┘
```

## ディレクトリ構成

```
.
├── src/leverage_survival_lab/
│   ├── data/         # ccxt経由のデータ取得・Parquet I/O
│   ├── engine/       # レバレッジエンジン(証拠金/清算/手数料)
│   ├── strategies/   # 5戦略(Random/SMA/RSI/Bollinger/Breakout)
│   ├── backtest/     # vectorbt連携・実験ハーネス
│   ├── analysis/     # 統計検定・可視化・Risk of Ruin
│   └── agent/        # Claude Code 自律エージェント連携
├── tests/            # pytest 単体・結合テスト
├── notebooks/        # 再現可能Jupyter
├── scripts/          # データ取得・実験起動 CLI
├── data/             # raw/processed (gitignore)
├── results/          # 実験結果 Parquet (gitignore)
└── docs/             # 仮説・設計・週次ノート
```

## クイックスタート

```bash
# 1. 仮想環境
python -m venv .venv
. .venv/Scripts/activate   # Windows: PowerShell は .\.venv\Scripts\Activate.ps1

# 2. 依存
pip install -e ".[dev]"

# 3. テスト
pytest

# 4. データ取得(Binance BTC/USDT 1h, 過去5年)
python -m leverage_survival_lab.data.fetch --symbol BTC/USDT --tf 1h --since 2020-01-01

# 5. ミニ実験
python scripts/run_mini_experiment.py
```

## ロードマップ(8週間)

| Week | フェーズ        | 主成果物                                       |
|------|----------------|----------------------------------------------|
| 1    | 基盤            | リポジトリ・環境・CI                          |
| 2    | データ          | OHLCV+Funding Parquet データセット            |
| 3    | レバエンジン    | 清算/手数料/ファンディングの正確なシミュレータ  |
| 4    | 戦略            | 5戦略 + バックテストハーネス                  |
| 5-6  | 自律実験        | Claude Code が 5万〜20万バックテストを自走    |
| 7    | 分析            | 4仮説の検定 + ヒートマップ                    |
| 8    | 発信            | ブログ・英語サマリ・(任意)プレプリント        |

## 免責事項

- 本リポジトリは投資助言ではありません
- シミュレーション結果は実取引の成果を保証しません
- 取引所APIは各社の利用規約を遵守し、読み取り専用・低頻度に限定します

## License

[MIT](LICENSE)
