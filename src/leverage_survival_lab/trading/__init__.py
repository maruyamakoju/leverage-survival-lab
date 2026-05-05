"""ペーパートレーディング — 仮想金で BTC をバンバン触るためのモジュール。"""
from __future__ import annotations

from .paper import PaperBroker, TradingSession

__all__ = ["PaperBroker", "TradingSession"]
