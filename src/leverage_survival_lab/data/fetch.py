"""ccxt 経由で OHLCV と funding rate を取得する CLI。

使用例:
    python -m leverage_survival_lab.data.fetch --symbol BTC/USDT --tf 1h --since 2020-01-01
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import click
import pandas as pd
from rich.console import Console
from rich.logging import RichHandler

from ..config import settings

logger = logging.getLogger(__name__)
console = Console()


def _setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _to_ms(dt_str: str) -> int:
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


def fetch_ohlcv(
    *,
    exchange_name: str,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int | None = None,
) -> pd.DataFrame:
    """OHLCV を ccxt で取得し DataFrame として返す。"""
    import ccxt

    ex_cls = getattr(ccxt, exchange_name)
    ex = ex_cls({"enableRateLimit": True})

    all_rows: list[list[float]] = []
    cursor = since_ms
    end = until_ms or int(datetime.now(timezone.utc).timestamp() * 1000)
    limit = 1500

    while cursor < end:
        rows = ex.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        # rate limit を尊重
        time.sleep(ex.rateLimit / 1000.0)
        logger.info("fetched %d rows up to %s", len(rows), datetime.fromtimestamp(last_ts / 1000, tz=timezone.utc))

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="ts").set_index("ts").sort_index()
    return df


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd")
    logger.info("saved %d rows to %s", len(df), path)


@click.command()
@click.option("--exchange", default=lambda: settings.default_exchange, show_default=True)
@click.option("--symbol", default=lambda: settings.default_symbol, show_default=True)
@click.option("--tf", "timeframe", default=lambda: settings.default_timeframe, show_default=True)
@click.option("--since", default="2020-01-01", show_default=True, help="取得開始日 (ISO)")
@click.option("--until", default=None, help="取得終了日 (ISO, 省略時は現在)")
def main(exchange: str, symbol: str, timeframe: str, since: str, until: str | None) -> None:
    """OHLCV を取得して Parquet 保存する。"""
    _setup_logging()
    since_ms = _to_ms(since)
    until_ms = _to_ms(until) if until else None
    df = fetch_ohlcv(
        exchange_name=exchange,
        symbol=symbol,
        timeframe=timeframe,
        since_ms=since_ms,
        until_ms=until_ms,
    )
    fname = f"{exchange}_{symbol.replace('/', '')}_{timeframe}.parquet"
    save_parquet(df, settings.data_raw_dir / fname)


if __name__ == "__main__":
    main()
