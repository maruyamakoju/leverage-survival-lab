"""ボラティリティ・エクスパンション × Donchian breakout 戦略。

仮説: トレンドは「ボラが平均より高い局面」で出やすい。低ボラ chop ではエッジが消える。
ATR (Average True Range) で現在のボラを測り、過去 vol_lookback の平均 ATR との比で
ボラ expansion 状態を判定。expansion 中のみ Donchian-style breakout に参加。

look-ahead 防止: ATR と rolling high/low は shift(1) し、bar t の close 確定時点で
利用可能な情報のみで判定。約定は bar t+1 open (バックテストエンジン側で処理)。
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from .base import Signal, Strategy


@dataclass
class VolBreakoutStrategy(Strategy):
    """ATR-aware Donchian breakout with volatility-expansion gate."""

    name: str = "vol_breakout"
    atr_period: int = 14         # ATR rolling 期間
    lookback: int = 20           # Donchian high/low rolling 期間
    k_atr: float = 1.5           # breakout 閾値: high + k*ATR / low - k*ATR
    vol_lookback: int = 100      # ボラ平均参照期間
    vol_threshold: float = 1.0   # 現 ATR / 平均 ATR > これでボラ expansion = 参加

    def generate(self, df: pd.DataFrame) -> Signal:
        if len(df) < max(self.atr_period, self.lookback, self.vol_lookback) + 2:
            return self._empty(df)

        high = df["high"]
        low = df["low"]
        close = df["close"]
        prev_close = close.shift(1)

        # True Range = max(H-L, |H-prevC|, |L-prevC|)
        tr = pd.concat(
            [
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        atr = tr.rolling(self.atr_period).mean()

        # ボラ expansion: 現 ATR が vol_lookback 平均より大きいか
        atr_avg = atr.rolling(self.vol_lookback).mean()
        vol_expansion = (atr / atr_avg) > self.vol_threshold

        # Donchian high/low (shift(1) で look-ahead 防止)
        donchian_high = high.rolling(self.lookback).max().shift(1)
        donchian_low = low.rolling(self.lookback).min().shift(1)
        atr_shift = atr.shift(1)

        upper = donchian_high + self.k_atr * atr_shift
        lower = donchian_low - self.k_atr * atr_shift

        sig = pd.Series(np.zeros(len(df), dtype=np.int8), index=df.index, name="signal")
        long_mask = (close > upper) & vol_expansion
        short_mask = (close < lower) & vol_expansion
        sig[long_mask] = 1
        sig[short_mask] = -1
        return sig.fillna(0).astype("int8")
