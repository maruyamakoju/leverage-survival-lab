"""グローバル設定。.env / 環境変数 / コードのデフォルトを統合する。"""
from __future__ import annotations

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT: Path = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """ランタイム設定。`.env` で上書き可能。"""

    model_config = SettingsConfigDict(env_file=".env", env_prefix="LSL_", extra="ignore")

    data_raw_dir: Path = Field(default=PROJECT_ROOT / "data" / "raw")
    data_processed_dir: Path = Field(default=PROJECT_ROOT / "data" / "processed")
    results_dir: Path = Field(default=PROJECT_ROOT / "results")

    default_exchange: str = "binance"
    default_symbol: str = "BTC/USDT"
    default_timeframe: str = "1h"

    initial_equity_usdt: float = 1_000_000.0
    random_seed: int = 42


settings = Settings()
