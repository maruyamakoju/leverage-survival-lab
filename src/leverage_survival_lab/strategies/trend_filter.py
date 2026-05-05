"""トレンド・フィルター戦略 — SMA 順張りに「直近モメンタムが強い時のみ参加」フィルタを追加。

実用度の高い "filtered SMA cross" の素朴版。素のSMAより取引数が少なく、勝率が高くなる
可能性がある(エッジ確認用)。
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from .base import Signal, Strategy


@dataclass
class TrendFilteredSMA(Strategy):
    """SMA クロスシグナルを、長期トレンド方向 (200 SMA vs price) と一致するものだけ採用。"""

    name: str = "trend_filtered_sma"
    fast: int = 20
    slow: int = 50
    trend: int = 200

    def generate(self, df: pd.DataFrame) -> Signal:
        close = df["close"]
        f = close.rolling(self.fast).mean()
        s = close.rolling(self.slow).mean()
        t = close.rolling(self.trend).mean()
        raw = (f > s).astype("int8") - (f < s).astype("int8")
        # トレンドフィルタ: close が 200SMA より上ならロングのみ、下ならショートのみ
        long_ok = close > t
        short_ok = close < t
        sig = pd.Series(0, index=df.index, dtype="int8")
        sig[(raw == 1) & long_ok] = 1
        sig[(raw == -1) & short_ok] = -1
        sig.name = "signal"
        return sig.fillna(0).astype("int8")
