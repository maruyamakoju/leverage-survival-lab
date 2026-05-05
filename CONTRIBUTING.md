# Contributing

Issue / PR 大歓迎です。本プロジェクトは「100倍レバの生存率を実証する」という性質上、**否定的結果を歓迎する**スタンスです。

## 開発フロー

1. Issue を立てる(または既存 Issue を選ぶ)
2. ブランチを切る (`git switch -c feat/your-feature`)
3. テストを書いてから実装する
4. `pytest` と `ruff check src tests` をパスすることを確認
5. PR を出す

## テスト

```bash
pytest                 # 全部
pytest -m "not integration"  # 高速ユニットのみ
pytest -m integration  # 結合のみ
pytest --cov=leverage_survival_lab
```

## 仮説の取り扱い

`docs/hypotheses.md` は **プレ・レジストレーション** 文書です。事後の改竄・削除は禁止。
新しい仮説は append で追加してください。
