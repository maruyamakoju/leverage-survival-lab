"""ファンディングレート逆張り戦略 — 高ファンディング(ロング過熱)→ ショート、逆もまた然り。

Perpetual swap のファンディングは過熱したサイドが支払う構造なので、
極端なファンディングは群衆心理の指標として使える可能性がある。
H3 を真に測定するため、エッジを持つ可能性のある戦略を追加。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import Signal, Strategy


@dataclass
class FundingFlipStrategy(Strategy):
    """ファンディングが大きい(ロング過熱)→ ショート、大きく負(ショート過熱)→ ロング。

    `funding_series` は OHLCV の index に reindex(forward fill)して使う。
    """

    name: str = "funding_flip"
    threshold: float = 0.0003  # 0.03% / 8h (年率約 33%)
    lookback: int = 24  # 24 時間平均ファンディングで判定
    funding_series: pd.Series | None = None  # 外部から注入

    def generate(self, df: pd.DataFrame) -> Signal:
        if self.funding_series is None:
            return self._empty(df)
        # df.index に合わせて 8h ステップを forward fill で展開
        f = self.funding_series.reindex(df.index, method="ffill")
        # lookback 時間の平均ファンディング
        f_avg = f.rolling(self.lookback).mean()
        sig = pd.Series(np.zeros(len(df), dtype=np.int8), index=df.index, name="signal")
        sig[f_avg > self.threshold] = -1   # 過熱ロング → ショート
        sig[f_avg < -self.threshold] = 1   # 過熱ショート → ロング
        return sig.astype("int8")
