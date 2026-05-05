"""合成 OHLCV 生成器 — テストとミニ実験で使う。

ジオメトリック・ブラウン運動 + 仮想 high/low を生成する単純なジェネレータ。
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def gbm_ohlcv(
    *,
    n_bars: int,
    drift: float = 0.0,
    vol: float = 0.01,
    start_price: float = 100.0,
    bar_freq: str = "h",
    start: str = "2024-01-01",
    seed: int = 0,
) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rets = rng.normal(drift, vol, size=n_bars)
    close = start_price * np.exp(np.cumsum(rets))
    high = close * (1 + np.abs(rng.normal(0, vol / 3, size=n_bars)))
    low = close * (1 - np.abs(rng.normal(0, vol / 3, size=n_bars)))
    open_ = np.concatenate([[start_price], close[:-1]])
    idx = pd.date_range(start, periods=n_bars, freq=bar_freq, tz="UTC")
    return pd.DataFrame({
        "open": open_, "high": high, "low": low, "close": close,
        "volume": rng.uniform(1, 10, size=n_bars),
    }, index=idx)


def crash_ohlcv(
    *,
    n_bars: int = 240,
    bar_freq: str = "h",
    start_price: float = 100.0,
    crash_at: int = 100,
    crash_pct: float = -0.30,
    drift: float = 0.0,
    vol: float = 0.01,
    seed: int = 0,
) -> pd.DataFrame:
    """途中で 1 バーだけ急落するシナリオ。レバ清算の単発テスト用。"""
    df = gbm_ohlcv(n_bars=n_bars, drift=drift, vol=vol,
                   start_price=start_price, bar_freq=bar_freq, seed=seed)
    if not 0 <= crash_at < n_bars:
        raise ValueError("crash_at out of range")
    # crash バーを差し替え
    pre_close = df["close"].iloc[crash_at - 1] if crash_at > 0 else start_price
    new_close = pre_close * (1 + crash_pct)
    df.iloc[crash_at, df.columns.get_loc("open")] = pre_close
    df.iloc[crash_at, df.columns.get_loc("low")] = new_close
    df.iloc[crash_at, df.columns.get_loc("high")] = pre_close
    df.iloc[crash_at, df.columns.get_loc("close")] = new_close
    # その後を recompute
    factor = df["close"] / df["close"].iloc[crash_at]
    # 単純化: crash_at 以降の close は new_close を起点にした GBM 続行に変更
    rng = np.random.default_rng(seed + 1)
    rets = rng.normal(drift, vol, size=max(0, n_bars - crash_at - 1))
    new_closes = new_close * np.exp(np.cumsum(rets))
    if len(new_closes) > 0:
        df.iloc[crash_at + 1 :, df.columns.get_loc("close")] = new_closes
        df.iloc[crash_at + 1 :, df.columns.get_loc("open")] = np.concatenate([[new_close], new_closes[:-1]])
        df.iloc[crash_at + 1 :, df.columns.get_loc("high")] = new_closes * 1.001
        df.iloc[crash_at + 1 :, df.columns.get_loc("low")] = new_closes * 0.999
    _ = factor  # unused; placeholder for future tweaks
    return df
