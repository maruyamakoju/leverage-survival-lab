"""自律リサーチエージェントの最小ループ骨格。

Claude Code を「外部実行系」とみなし、ここでは検査可能な決定論的 loop だけを書く。
実際の Claude 連携は `scripts/run_agent.py` で外側から駆動する。

設計:
- `Hypothesis` … 検証したい問い + 操作変数の指定
- `Experiment`  … 単一実験(grid + summary + 検定)
- `History`    … 履歴を保存し次回の入力にする
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass
class Hypothesis:
    name: str
    description: str
    operationalization: str
    rejection_rule: str

    def to_dict(self) -> dict[str, str]:
        return {
            "name": self.name,
            "description": self.description,
            "operationalization": self.operationalization,
            "rejection_rule": self.rejection_rule,
        }


@dataclass
class Experiment:
    hypothesis: Hypothesis
    grid_spec: dict[str, Any]
    seed: int
    started_at: datetime
    finished_at: datetime | None = None
    grid_path: Path | None = None
    report_path: Path | None = None
    insight: str = ""


@dataclass
class History:
    experiments: list[Experiment] = field(default_factory=list)
    log_path: Path = Path("results") / "agent_log.jsonl"

    def append(self, exp: Experiment) -> None:
        self.experiments.append(exp)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "hypothesis": exp.hypothesis.to_dict(),
                "grid_spec": exp.grid_spec,
                "seed": exp.seed,
                "grid_path": str(exp.grid_path) if exp.grid_path else None,
                "report_path": str(exp.report_path) if exp.report_path else None,
                "insight": exp.insight,
            }, ensure_ascii=False) + "\n")


def initial_hypotheses() -> list[Hypothesis]:
    """プレ・レジストレーション済の 4 仮説を Hypothesis dataclass として返す。"""
    return [
        Hypothesis(
            name="H1",
            description="100倍レバの30日生存率はいかなる損切ルールでも10%未満",
            operationalization="100x × 全 stop_loss 水準 × 全戦略で N=100 の MC、生存率の Wilson 95%CI 上限を比較",
            rejection_rule="いずれかセルで CI 上限 ≥ 10%",
        ),
        Hypothesis(
            name="H2",
            description="各レバ倍率に最適な損切ラインが内点解として存在する",
            operationalization="各 (strategy, lev) で stop_loss を 5 水準スイープ。最大値が境界以外に出るか",
            rejection_rule="ほぼすべての (strategy, lev) で最大値が端点(loose=NaN もしくは最も tight=-0.5%)に集中する",
        ),
        Hypothesis(
            name="H3",
            description="戦略のエッジはレバ閾値を超えると消失する",
            operationalization="各戦略で平均 log-return がレバとともに正→負に転じる閾値を推定",
            rejection_rule="閾値が < 10x または > 20x の場合、H3 の数値予測は外れ",
        ),
        Hypothesis(
            name="H4",
            description="50倍以上ではナイーブ戦略 vs ランダム に統計的有意差なし",
            operationalization="50x, 100x で各戦略 vs ランダム の 2 比率検定 + Bonferroni",
            rejection_rule="補正後 α で 1 つでも棄却",
        ),
    ]
