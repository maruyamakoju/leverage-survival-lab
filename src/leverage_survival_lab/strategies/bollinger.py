"""ボリンジャーバンド回帰戦略。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import Signal, Strategy


@dataclass
class BollingerStrategy(Strategy):
    name: str = "bollinger"
    window: int = 20
    n_std: float = 2.0

    def generate(self, df: pd.DataFrame) -> Signal:
        close = df["close"]
        ma = close.rolling(self.window).mean()
        sd = close.rolling(self.window).std(ddof=0)
        upper = ma + self.n_std * sd
        lower = ma - self.n_std * sd
        sig = pd.Series(0, index=df.index, dtype="int8")
        sig[close < lower] = 1
        sig[close > upper] = -1
        sig.name = "signal"
        return sig.fillna(0).astype("int8")
