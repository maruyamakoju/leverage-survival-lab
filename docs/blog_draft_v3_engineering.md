# 87,325 回のバックテストを Windows + Python で回そうとしてハマった話

## TL;DR

100倍レバの生存率を実証するプロジェクトで、**Windows 上で Python 3.11 + pandas + numpy が稀にセグフォルト**する問題に遭遇。デバッグの過程で「pandas 3.0 の list-of-dict コンストラクタ回帰」「長時間プロセスのメモリ蓄積による native crash」など複数の症状が混在していた。最終的に `subprocess` でプロセス分割 + リトライ + DataFrame 構築方法の変更で 269,963 回のバックテストを完走させた。

本記事は、データサイエンスをやっていてハマる人の参考用。

---

## 環境

- Windows 11 Home (10.0.26200)
- Python 3.11.9 (公式 .exe インストール)
- pandas 3.0.2 → 2.3.3(後にダウングレード)
- numpy 2.4.4(numpy 1.26 でも同じ症状)
- ccxt, vectorbt 不使用(自前実装)

## 症状 1: pandas 3.0 のセグフォルト

```python
# trades = [
#   {"bar": 5, "action": "open", "side": "long", "price": 100.0},
#   {"bar": 12, "action": "stop_loss", "side": "long", "price": 98.0, "pnl": -2_000_000},
# ]
trade_df = pd.DataFrame(trades)
# Windows fatal exception: access violation
# in pandas/core/internals/construction.py: _list_of_dict_to_arrays
```

**原因**: pandas 3.0.2 の `_list_of_dict_to_arrays` がキー集合の異なる dict のリストでクラッシュする回帰(再現性あり、同じスクリプトで N=100 を何度か走らせると確率的に発生)。

**対策**: 
1. dict のスキーマを統一する(`pnl` フィールドを open trade にも `None` で持たせる)
2. pandas を `<3` にピン留め
3. 列ごとに list を集めて `pd.DataFrame(dict_of_lists)` 経由で構築する `_safe_records_to_df` を実装

`pyproject.toml`:
```toml
"pandas>=2.2,<3",  # pandas 3.0.x にセグフォルト不具合
```

## 症状 2: 長時間プロセスでの累積 native crash

```python
for i in range(50_000):
    df = ...
    res = run_backtest(df, sig, cfg)
# i=672 あたりで segfault, 場所はランダム
# (pd.Series 構築だったり、numpy indexing だったり)
```

**原因(推測)**: numpy/pandas の C 拡張が、長時間プロセスでメモリを断片的に解放/再確保する中で、稀にダブルフリー的な状態に陥る(と思われる)。詳細未特定。

**対策**: subprocess で「200 windows ごと」にプロセスを完全リサイクルする `scripts/run_realdata_chunked.py` を実装。

```python
for c in range(n_chunks):
    cmd = [py, "scripts/run_realdata_experiment.py", "--n-windows", "200", "--name", f"chunk{c}"]
    for attempt in range(3):
        result = subprocess.run(cmd)
        if result.returncode == 0:
            break  # 成功
        # リトライ: 別 seed で再実行
```

これで 10 chunks 中 9 chunks 成功(残り 1 つも 4 回試行で諦める設計)。トータル 1,800 windows × 175 セル = **314,825 sims** を回せた(うち 269,963 が valid、~14% は intra-chunk の native crash で error フラグ付き)。

## 症状 3: 100x 清算価格の docstring 誤記

```python
def liquidation_price(...):
    """
    >>> round(liquidation_price(entry=100.0, leverage=100, side=Side.LONG, mm=0.005), 4)
    99.005   # ← この期待値が間違い
    """
    ...
```

**原因**: 単純な数式ミス。100倍レバで 0.5% mm なら、(1/100 - 0.005) = 0.5% 下落で清算 → 99.5。99.005 ではない。

**対策**: 単体テスト書いた瞬間に発見、正しい値(99.5)に修正。

教訓: docstring に書いた数式は**必ずテストで再検証**する。一目で正しく見えるが、AIが書いた場合も人間が書いた場合も微妙に間違うことがある。

## 症状 4: rich の console.print が出力を阻害?

`run_grid_realdata` で `tqdm` の進捗バーが標準出力をフラッディングして、リダイレクト先のログファイルが膨れ上がってプロセスが詰まる現象。

**対策**: `tqdm(it, mininterval=2.0, miniters=500)` で更新頻度を抑制。tty でない時は適度に間引かれる。

## 学んだこと

1. **Python の C 拡張は long-lived プロセスでブラックボックス化する** — Linux なら gdb で踏み込むが、Windows ではしんどい
2. **subprocess による分離が一番安い** — チャンク化 + リトライ + 結果マージは、汚いが効く
3. **数値ミスはテストでしか発見できない** — docstring の期待値も自動検証対象に
4. **DataFrame コンストラクタは入力スキーマに敏感** — 不均一な dict リストは避けるか、dict-of-lists 経由で

## 結果

最終的に **269,963 回**のバックテスト完走。100倍レバ 30日生存率の Wilson 95% CI 上限は **0.27%**。BTC/ETH/SOL の3通貨でも同じ結論。

コードは MIT で全公開:[github.com/maruyamakoju/leverage-survival-lab](https://github.com/maruyamakoju/leverage-survival-lab)

## 注

本記事は投資助言ではない。
