"""データ品質チェック — 欠損・異常値・連続性。"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class QualityReport:
    n_rows: int
    n_duplicates: int
    n_gaps: int
    largest_gap: pd.Timedelta | None
    n_negative_returns_extreme: int  # |return| > 50% のバー数
    n_zero_volume: int
    expected_freq: str
    pct_complete: float

    def is_healthy(self, *, max_gaps: int = 5, min_complete: float = 0.99) -> bool:
        return self.n_gaps <= max_gaps and self.pct_complete >= min_complete


def expected_timedelta(timeframe: str) -> pd.Timedelta:
    """ccxt 互換の timeframe 文字列を Timedelta に変換。"""
    unit = timeframe[-1]
    val = int(timeframe[:-1])
    if unit == "m":
        return pd.Timedelta(minutes=val)
    if unit == "h":
        return pd.Timedelta(hours=val)
    if unit == "d":
        return pd.Timedelta(days=val)
    raise ValueError(f"unknown timeframe unit in {timeframe}")


def assess_ohlcv(df: pd.DataFrame, timeframe: str) -> QualityReport:
    if df.empty:
        return QualityReport(0, 0, 0, None, 0, 0, timeframe, 0.0)

    expected = expected_timedelta(timeframe)
    diffs = df.index.to_series().diff().dropna()
    gaps = diffs[diffs > expected * 1.5]

    rets = df["close"].pct_change().abs()
    n_extreme = int((rets > 0.5).sum())

    n_dup = int(df.index.duplicated().sum())
    n_zero_vol = int((df["volume"] == 0).sum())

    expected_n = int((df.index.max() - df.index.min()) / expected) + 1
    pct = len(df) / expected_n if expected_n > 0 else 1.0

    largest = gaps.max() if not gaps.empty else None
    return QualityReport(
        n_rows=len(df),
        n_duplicates=n_dup,
        n_gaps=len(gaps),
        largest_gap=largest,
        n_negative_returns_extreme=n_extreme,
        n_zero_volume=n_zero_vol,
        expected_freq=timeframe,
        pct_complete=pct,
    )


def fill_gaps_forward(df: pd.DataFrame, timeframe: str) -> pd.DataFrame:
    """欠損バーを直前の close で前進補完する(open=high=low=close, volume=0)。
    バックテスト時に index が連続していることを保証するためのユーティリティ。
    """
    if df.empty:
        return df
    expected = expected_timedelta(timeframe)
    full_idx = pd.date_range(df.index.min(), df.index.max(), freq=expected)
    df2 = df.reindex(full_idx)
    closes = df2["close"].ffill()
    for col in ("open", "high", "low", "close"):
        df2[col] = df2[col].fillna(closes)
    df2["volume"] = df2["volume"].fillna(0.0)
    df2.index.name = "ts"
    return df2


def detect_regimes(df: pd.DataFrame, *, window: int = 24 * 30) -> pd.Series:
    """30日窓のリターンとボラから単純な regime ラベルを返す: trend_up/trend_down/range/crash。"""
    if df.empty:
        return pd.Series([], name="regime")
    ret = df["close"].pct_change()
    cum = ret.rolling(window).sum()

    label = pd.Series("range", index=df.index)
    label[cum > 0.30] = "trend_up"
    label[cum < -0.30] = "trend_down"
    label[(ret < -0.10)] = "crash"  # 単一バー -10% 超
    return label.rename("regime")
