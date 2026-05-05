"""ランダムエントリー戦略 — H4 帰無比較用のベースライン。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import Signal, Strategy


@dataclass
class RandomStrategy(Strategy):
    """各バーで確率 `p_long`, `p_short` で long/short, 残りは flat。"""

    name: str = "random"
    p_long: float = 0.05
    p_short: float = 0.05
    seed: int = 0

    def generate(self, df: pd.DataFrame) -> Signal:
        rng = np.random.default_rng(self.seed)
        u = rng.random(len(df))
        sig = np.zeros(len(df), dtype=np.int8)
        sig[u < self.p_long] = 1
        sig[(u >= self.p_long) & (u < self.p_long + self.p_short)] = -1
        return pd.Series(sig, index=df.index, name="signal")
