"""RSI 逆張り戦略。"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import Signal, Strategy


def _rsi(close: pd.Series, period: int) -> pd.Series:
    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = -delta.clip(upper=0.0)
    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    return 100.0 - (100.0 / (1.0 + rs))


@dataclass
class RSIStrategy(Strategy):
    """RSI が overbought ↑ → short、oversold ↓ → long の素朴な mean-reversion。"""

    name: str = "rsi"
    period: int = 14
    overbought: float = 70.0
    oversold: float = 30.0

    def generate(self, df: pd.DataFrame) -> Signal:
        rsi = _rsi(df["close"], self.period)
        sig = pd.Series(0, index=df.index, dtype="int8")
        sig[rsi < self.oversold] = 1
        sig[rsi > self.overbought] = -1
        sig.name = "signal"
        return sig.fillna(0).astype("int8")
