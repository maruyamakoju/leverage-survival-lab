"""価格フィード — replay (過去データ) と live (Binance polling)。"""
from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd


def replay_feed(
    df: pd.DataFrame, *, start: str | None = None, end: str | None = None,
) -> Iterator[dict[str, Any]]:
    """OHLCV DataFrame を逐次 yield する。"""
    if start is not None:
        df = df.loc[df.index >= pd.Timestamp(start, tz="UTC")]
    if end is not None:
        df = df.loc[df.index <= pd.Timestamp(end, tz="UTC")]
    for ts, row in df.iterrows():
        yield {
            "price": float(row["close"]),
            "high": float(row["high"]),
            "low": float(row["low"]),
            "ts": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
        }


def random_window_replay(
    df: pd.DataFrame, *, window_bars: int, seed: int | None = None,
) -> Iterator[dict[str, Any]]:
    """過去データからランダムに連続 window_bars を抽出して yield。"""
    import numpy as np
    rng = np.random.default_rng(seed)
    if window_bars >= len(df):
        raise ValueError("window_bars must be < len(df)")
    s = int(rng.integers(0, len(df) - window_bars))
    sub = df.iloc[s : s + window_bars]
    yield from replay_feed(sub)


def live_binance_feed(
    symbol: str = "BTC/USDT", *, poll_seconds: float = 5.0, market_type: str = "future",
) -> Iterator[dict[str, Any]]:
    """Binance のリアルタイム ticker を polling して yield する。

    Note: 5 秒ごとに 1 ticker を fetch。レート制限内。
    SL/TP 判定で high/low が必要だが、ticker からは current price だけなので
    high=low=price で渡す(intra-tick 範囲が狭いと仮定)。
    """
    import ccxt

    ex_cls = ccxt.binance
    ex = ex_cls({"enableRateLimit": True, "options": {"defaultType": market_type}})

    while True:
        try:
            t = ex.fetch_ticker(symbol)
            price = float(t["last"])
            ts = datetime.fromtimestamp(t["timestamp"] / 1000, tz=UTC).isoformat() if t.get("timestamp") else datetime.now(UTC).isoformat()
            yield {"price": price, "high": price, "low": price, "ts": ts}
        except Exception as e:
            yield {"price": 0.0, "high": 0.0, "low": 0.0, "ts": datetime.now(UTC).isoformat(),
                   "error": str(e)}
        time.sleep(poll_seconds)


def load_local_btc(timeframe: str = "1h") -> pd.DataFrame:
    """ローカルに保存された BTC/USDT のデータをロードする。"""
    p = Path(f"data/raw/binance_BTCUSDT_{timeframe}.parquet")
    if not p.exists():
        raise FileNotFoundError(
            f"missing {p}. run: python -m leverage_survival_lab.data.fetch ohlcv --tf {timeframe}"
        )
    return pd.read_parquet(p)
