"""ccxt 経由で OHLCV と funding rate を取得する CLI。

使用例:
    python -m leverage_survival_lab.data.fetch ohlcv --symbol BTC/USDT --tf 1h --since 2020-01-01
    python -m leverage_survival_lab.data.fetch funding --symbol BTC/USDT --since 2020-01-01

出力: Parquet (zstd 圧縮)、`data/raw/{exchange}_{symbol}_{tf}.parquet` 等。
再実行に強く、既存ファイルがあれば最終 ts の翌バーから増分取得する。
"""
from __future__ import annotations

import logging
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import click
import pandas as pd
from rich.console import Console
from rich.logging import RichHandler
from tenacity import retry, stop_after_attempt, wait_exponential

from ..config import settings

logger = logging.getLogger(__name__)
console = Console()


def _setup_logging() -> None:
    if not logging.getLogger().handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(message)s",
            datefmt="[%X]",
            handlers=[RichHandler(console=console, rich_tracebacks=True)],
        )


def _to_ms(dt_str: str) -> int:
    dt = datetime.fromisoformat(dt_str).replace(tzinfo=UTC)
    return int(dt.timestamp() * 1000)


def _ohlcv_path(exchange: str, symbol: str, timeframe: str) -> Path:
    fname = f"{exchange}_{symbol.replace('/', '')}_{timeframe}.parquet"
    return settings.data_raw_dir / fname


def _funding_path(exchange: str, symbol: str) -> Path:
    fname = f"{exchange}_{symbol.replace('/', '')}_funding.parquet"
    return settings.data_raw_dir / fname


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def _fetch_ohlcv_chunk(ex: Any, symbol: str, timeframe: str, since: int, limit: int) -> list[list[float]]:
    return ex.fetch_ohlcv(symbol, timeframe=timeframe, since=since, limit=limit)


def fetch_ohlcv(
    *,
    exchange_name: str,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int | None = None,
    market_type: str = "future",  # "spot" or "future" (USDT-M perp)
) -> pd.DataFrame:
    """OHLCV を ccxt で取得し DataFrame として返す。"""
    import ccxt

    ex_cls = getattr(ccxt, exchange_name)
    ex = ex_cls({"enableRateLimit": True, "options": {"defaultType": market_type}})

    all_rows: list[list[float]] = []
    cursor = since_ms
    end = until_ms or int(datetime.now(UTC).timestamp() * 1000)
    limit = 1500

    while cursor < end:
        rows = _fetch_ohlcv_chunk(ex, symbol, timeframe, cursor, limit)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = rows[-1][0]
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
        if len(all_rows) % (limit * 5) == 0:
            logger.info("ohlcv fetched %d rows up to %s",
                        len(all_rows),
                        datetime.fromtimestamp(last_ts / 1000, tz=UTC))

    df = pd.DataFrame(all_rows, columns=["ts", "open", "high", "low", "close", "volume"])
    if df.empty:
        return df
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="ts").set_index("ts").sort_index()
    return df


@retry(stop=stop_after_attempt(5), wait=wait_exponential(multiplier=1, min=1, max=30))
def _fetch_funding_chunk(ex: Any, symbol: str, since: int, limit: int) -> list[dict[str, Any]]:
    return ex.fetch_funding_rate_history(symbol, since=since, limit=limit)


def fetch_funding(
    *,
    exchange_name: str,
    symbol: str,
    since_ms: int,
    until_ms: int | None = None,
) -> pd.DataFrame:
    """ファンディングレート履歴を取得し DataFrame として返す。"""
    import ccxt

    ex_cls = getattr(ccxt, exchange_name)
    ex = ex_cls({"enableRateLimit": True, "options": {"defaultType": "future"}})

    all_rows: list[dict[str, Any]] = []
    cursor = since_ms
    end = until_ms or int(datetime.now(UTC).timestamp() * 1000)
    limit = 1000

    while cursor < end:
        rows = _fetch_funding_chunk(ex, symbol, cursor, limit)
        if not rows:
            break
        all_rows.extend(rows)
        last_ts = int(rows[-1]["timestamp"])
        if last_ts <= cursor:
            break
        cursor = last_ts + 1
        time.sleep(ex.rateLimit / 1000.0)
        if len(all_rows) % (limit * 3) == 0:
            logger.info("funding fetched %d rows up to %s",
                        len(all_rows),
                        datetime.fromtimestamp(last_ts / 1000, tz=UTC))

    if not all_rows:
        return pd.DataFrame()
    df = pd.DataFrame([
        {"ts": r["timestamp"], "rate": float(r.get("fundingRate") or 0.0)}
        for r in all_rows
    ])
    df["ts"] = pd.to_datetime(df["ts"], unit="ms", utc=True)
    df = df.drop_duplicates(subset="ts").set_index("ts").sort_index()
    return df


def save_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(path, compression="zstd")
    logger.info("saved %d rows -> %s", len(df), path)


def load_or_empty(path: Path) -> pd.DataFrame:
    if path.exists():
        return pd.read_parquet(path)
    return pd.DataFrame()


def incremental_fetch_ohlcv(
    *, exchange_name: str, symbol: str, timeframe: str,
    default_since: int, until_ms: int | None = None,
    market_type: str = "future",
) -> pd.DataFrame:
    """既存ファイルがあれば末尾から、なければ default_since から取得して上書き保存。"""
    path = _ohlcv_path(exchange_name, symbol, timeframe)
    existing = load_or_empty(path)
    if not existing.empty:
        last_ts_ms = int(existing.index.max().timestamp() * 1000)
        since_ms = last_ts_ms + 1
        logger.info("resume from %s", existing.index.max())
    else:
        since_ms = default_since
        logger.info("fresh fetch from %s",
                    datetime.fromtimestamp(since_ms / 1000, tz=UTC))
    new_df = fetch_ohlcv(
        exchange_name=exchange_name, symbol=symbol, timeframe=timeframe,
        since_ms=since_ms, until_ms=until_ms, market_type=market_type,
    )
    combined = pd.concat([existing, new_df]).drop_duplicates() if not new_df.empty else existing
    combined = combined.sort_index() if not combined.empty else combined
    if not combined.empty:
        save_parquet(combined, path)
    return combined


def incremental_fetch_funding(
    *, exchange_name: str, symbol: str,
    default_since: int, until_ms: int | None = None,
) -> pd.DataFrame:
    path = _funding_path(exchange_name, symbol)
    existing = load_or_empty(path)
    if not existing.empty:
        last_ts_ms = int(existing.index.max().timestamp() * 1000)
        since_ms = last_ts_ms + 1
        logger.info("resume funding from %s", existing.index.max())
    else:
        since_ms = default_since
    new_df = fetch_funding(
        exchange_name=exchange_name, symbol=symbol,
        since_ms=since_ms, until_ms=until_ms,
    )
    combined = pd.concat([existing, new_df]).drop_duplicates() if not new_df.empty else existing
    combined = combined.sort_index() if not combined.empty else combined
    if not combined.empty:
        save_parquet(combined, path)
    return combined


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.group()
def cli() -> None:
    """Leverage Survival Lab — データ取得 CLI"""
    _setup_logging()


@cli.command("ohlcv")
@click.option("--exchange", default=lambda: settings.default_exchange, show_default=True)
@click.option("--symbol", default=lambda: settings.default_symbol, show_default=True)
@click.option("--tf", "timeframe", default=lambda: settings.default_timeframe, show_default=True)
@click.option("--since", default="2020-01-01", show_default=True)
@click.option("--until", default=None)
@click.option("--market", default="future", type=click.Choice(["spot", "future"]))
def cli_ohlcv(exchange: str, symbol: str, timeframe: str, since: str, until: str | None, market: str) -> None:
    df = incremental_fetch_ohlcv(
        exchange_name=exchange, symbol=symbol, timeframe=timeframe,
        default_since=_to_ms(since),
        until_ms=_to_ms(until) if until else None,
        market_type=market,
    )
    logger.info("OHLCV total rows: %d", len(df))


@cli.command("funding")
@click.option("--exchange", default=lambda: settings.default_exchange, show_default=True)
@click.option("--symbol", default=lambda: settings.default_symbol, show_default=True)
@click.option("--since", default="2020-01-01", show_default=True)
@click.option("--until", default=None)
def cli_funding(exchange: str, symbol: str, since: str, until: str | None) -> None:
    df = incremental_fetch_funding(
        exchange_name=exchange, symbol=symbol,
        default_since=_to_ms(since),
        until_ms=_to_ms(until) if until else None,
    )
    logger.info("Funding total rows: %d", len(df))


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
