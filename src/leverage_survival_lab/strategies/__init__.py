"""シグナル生成戦略。Signal は {-1, 0, +1} の系列を返すだけにし、
レバレッジや損切等のリスク管理は backtest 側で別途適用する。"""
from __future__ import annotations

from .base import Signal, Strategy
from .breakout import BreakoutStrategy
from .bollinger import BollingerStrategy
from .random_strategy import RandomStrategy
from .rsi import RSIStrategy
from .sma_cross import SMACrossStrategy

__all__ = [
    "BollingerStrategy",
    "BreakoutStrategy",
    "RSIStrategy",
    "RandomStrategy",
    "SMACrossStrategy",
    "Signal",
    "Strategy",
]
