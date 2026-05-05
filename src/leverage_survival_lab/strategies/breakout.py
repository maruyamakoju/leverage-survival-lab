"""ドンチャン型ブレイクアウト戦略。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import Signal, Strategy


@dataclass
class BreakoutStrategy(Strategy):
    name: str = "breakout"
    window: int = 20

    def generate(self, df: pd.DataFrame) -> Signal:
        high_n = df["high"].rolling(self.window).max().shift(1)
        low_n = df["low"].rolling(self.window).min().shift(1)
        sig = pd.Series(0, index=df.index, dtype="int8")
        sig[df["close"] > high_n] = 1
        sig[df["close"] < low_n] = -1
        sig.name = "signal"
        return sig.fillna(0).astype("int8")
