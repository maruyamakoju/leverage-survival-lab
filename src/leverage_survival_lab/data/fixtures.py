"""既知クラッシュシナリオの DataFrame を切り出すユーティリティ。

レバレッジエンジンの再現性検証(Cross/Isolated 100x が想定通り 0 になるか)に使う。
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

# (label, start_iso, end_iso, description)
KNOWN_SCENARIOS: list[tuple[str, str, str, str]] = [
    ("covid_crash_2020", "2020-03-09", "2020-03-20", "COVID パニック売り、BTC -50%"),
    ("may_2021_flush", "2021-05-12", "2021-05-23", "BTC -50% フラッシュ、清算連鎖"),
    ("ftx_collapse_2022", "2022-11-04", "2022-11-15", "FTX 破綻、数日にわたる連鎖下落"),
    ("luna_collapse_2022", "2022-05-08", "2022-05-15", "UST デペッグ、暗号全体の急落"),
    ("bull_run_2021", "2021-01-01", "2021-04-15", "BTC 三ヶ月で +120% トレンド期"),
]


def scenario_window(scenario: str) -> tuple[pd.Timestamp, pd.Timestamp]:
    for label, start, end, _ in KNOWN_SCENARIOS:
        if label == scenario:
            return (
                pd.Timestamp(start, tz="UTC"),
                pd.Timestamp(end, tz="UTC"),
            )
    raise KeyError(f"unknown scenario: {scenario}")


def slice_scenario(df: pd.DataFrame, scenario: str) -> pd.DataFrame:
    start, end = scenario_window(scenario)
    return df.loc[(df.index >= start) & (df.index <= end)].copy()


def list_scenarios() -> list[dict[str, str]]:
    return [
        {"name": l, "start": s, "end": e, "description": d}
        for l, s, e, d in KNOWN_SCENARIOS
    ]
