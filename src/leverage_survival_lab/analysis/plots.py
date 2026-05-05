"""可視化ヘルパー — ヒートマップ・分布・equity curve。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def survival_heatmap(
    summary: pd.DataFrame,
    *,
    strategy: str,
    title: str | None = None,
    save_to: Path | None = None,
):
    """`survival_summary` の結果から (leverage × stop_loss) のヒートマップを描画。

    matplotlib に依存(plotly 版は別途)。
    """
    import matplotlib.pyplot as plt

    sub = summary[summary["strategy"] == strategy]
    pivot = sub.pivot(index="leverage", columns="stop_loss", values="survival")
    pivot = pivot.sort_index().sort_index(axis=1, na_position="last")

    fig, ax = plt.subplots(figsize=(8, 5))
    im = ax.imshow(pivot.values, aspect="auto", cmap="RdYlGn", vmin=0, vmax=1)

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels([f"{c*100:.1f}%" if isinstance(c, float) else "None" for c in pivot.columns])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels([f"{int(v)}x" for v in pivot.index])
    ax.set_xlabel("Stop Loss")
    ax.set_ylabel("Leverage")
    ax.set_title(title or f"Survival Rate — {strategy}")

    for i in range(pivot.shape[0]):
        for j in range(pivot.shape[1]):
            v = pivot.values[i, j]
            if not np.isnan(v):
                ax.text(j, i, f"{v*100:.0f}%", ha="center", va="center",
                        color="black" if v > 0.5 else "white", fontsize=9)

    fig.colorbar(im, ax=ax, label="Survival rate")
    fig.tight_layout()
    if save_to is not None:
        save_to.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(save_to, dpi=150, bbox_inches="tight")
    return fig
