"""戦略基底。"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypeAlias

import numpy as np
import pandas as pd

# +1: long, -1: short, 0: flat
Signal: TypeAlias = pd.Series


@dataclass
class Strategy(ABC):
    """戦略基底。`generate(df)` は OHLCV DataFrame を受け取り
    {-1, 0, +1} の Signal Series を返す。

    重要: シグナルは bar t の close 確定後に生成され、
    バックテスト側で bar t+1 の open で約定する想定。"""

    name: str = "base"

    @abstractmethod
    def generate(self, df: pd.DataFrame) -> Signal:
        ...

    @staticmethod
    def _empty(df: pd.DataFrame) -> Signal:
        return pd.Series(np.zeros(len(df), dtype=np.int8), index=df.index, name="signal")
