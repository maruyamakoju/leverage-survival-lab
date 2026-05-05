# Pre-Registered Hypotheses

> **Pre-registration date**: 2026-05-05
> **Lock policy**: 本ファイルは実験開始前に git にコミットし、commit hash を記録する。事後の修正は **append-only**(取り消し線+理由+新仮説の追加)とし、過去の仮説は決して削除・改竄しない。

## H1: レバレッジと生存率の単調関係

**主張**: 30日間の口座生存率は、レバレッジ倍率に対して単調減少する。100倍レバの30日生存率は、いかなる損切ルールの下でも 10% 未満である。

**operationalization**:
- 生存率 = 30日経過時点で初期証拠金の 10% 以上を保持している比率
- 各 (leverage, stop_loss, strategy, asset, regime) セルで N=100 のモンテカルロ反復
- レバ水準: {1, 2, 5, 10, 25, 50, 100}
- 損切水準: {-0.5%, -1%, -2%, -5%, -10%, none}

**統計的検定**:
- 単調性: Spearman rank correlation (ρ) と Mann-Kendall test
- 100倍レバ: 全損切水準で Wilson score 95%CI の上限が 10% 未満であること

**棄却ルール**: いずれかの損切水準で生存率の Wilson 95%CI 下限 ≥ 10% の場合、H1 棄却。

---

## H2: 損切ラインの最適点

**主張**: 各レバレッジ倍率に対し、生存率(あるいは終端 expected log return)を最大化する損切ラインが内点解として存在する。

**operationalization**:
- 各レバ水準で損切水準を 6 点グリッドで評価
- 「内点解」= 最も緩い水準(none)でも最もタイトな水準(-0.5%)でもない位置に最大値があること

**統計的検定**:
- 各セルの平均終端残高に対し、最大値の位置を bootstrap で推定
- 最適点が境界以外にある確率 > 0.95 で支持

---

## H3: 戦略エッジの消失閾値

**主張**: 正のシャープレシオ(stand-alone, レバ1倍)を持つ戦略でも、レバが 10〜20倍を超えると、取引コスト(手数料・スプレッド・スリッページ)とボラティリティドラッグにより、期待 log-return が負に転じる。

**operationalization**:
- まずレバ1倍で各戦略のSharpeを推定 → Sharpe>0 の戦略のみH3対象
- その戦略を各レバ水準で動かし、終端 log-return の平均と95%CI を記録
- 期待 log-return が初めて負になるレバ水準を「閾値」として記録

**統計的検定**:
- 閾値 ∈ [10, 20] かどうかを N=100 のシナリオで検定
- 閾値 < 10 → H3a(コスト過小評価の可能性)、 > 20 → H3b(より頑健)

---

## H4: ランダム戦略との同値性

**主張**: 高レバ(50倍以上)領域では、ナイーブ戦略の生存率はランダムエントリーと統計的有意差なし(α=0.05, multiple-testing 補正後)。

**operationalization**:
- ナイーブ戦略 4種(SMA/RSI/Bollinger/Breakout) vs ランダム
- 各ペア (strategy, random) ×レバ {50, 100} で生存率の差を two-sample test
- Bonferroni 補正(8 比較なので α/8 = 0.00625)

**統計的検定**:
- Welch's t-test または bootstrap permutation
- すべての比較で p > 0.00625 のとき H4 支持

---

## バイアス対策(全仮説共通)

| バイアス             | 対策                                                          |
|---------------------|--------------------------------------------------------------|
| Look-ahead          | バー終値で判断 → 次バー始値で約定。エンジン側で強制         |
| Survivorship        | 暗号は影響限定だが、上場廃止トークンも universe に含める検討 |
| Multiple testing    | Deflated Sharpe Ratio (Bailey & López de Prado), Bonferroni  |
| Walk-forward        | rolling 24mo / 6mo OOS の繰り返し                            |
| Data snooping       | パラメータ最適化は IS のみ、評価は OOS                       |
| Monte Carlo perm    | 戦略シグナルのランダム並べ替えで帰無分布を構築               |

## Lock 確認

- [ ] git commit hash: _(初回コミット後に記入)_
- [ ] 上記 commit を main ブランチに push
- [ ] 公開 URL(GitHub): _(push後に記入)_
