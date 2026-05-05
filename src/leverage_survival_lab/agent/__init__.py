"""Claude Code 自律エージェント連携。

`loop.py` で骨格を提供。実際の Claude Code 駆動は外部スクリプトから行う。
"""
from __future__ import annotations

from .loop import Experiment, History, Hypothesis, initial_hypotheses

__all__ = ["Experiment", "History", "Hypothesis", "initial_hypotheses"]
