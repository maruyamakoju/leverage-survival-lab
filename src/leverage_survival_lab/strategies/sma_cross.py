"""SMA クロス戦略。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import Signal, Strategy


@dataclass
class SMACrossStrategy(Strategy):
    name: str = "sma_cross"
    fast: int = 20
    slow: int = 50

    def generate(self, df: pd.DataFrame) -> Signal:
        if self.fast >= self.slow:
            raise ValueError("fast must be < slow")
        close = df["close"]
        f = close.rolling(self.fast).mean()
        s = close.rolling(self.slow).mean()
        sig = (f > s).astype("int8") - (f < s).astype("int8")
        sig.name = "signal"
        return sig.fillna(0).astype("int8")
