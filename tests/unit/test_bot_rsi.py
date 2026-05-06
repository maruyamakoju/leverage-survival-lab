"""bot._rsi() のエッジケース回帰テスト。

V3.6 ライブ走行で `'int' object is not subscriptable` の TypeError が _rsi() で
発生し、4 時間動いていた bot が停止した。原因再現は難しいが、deque に予期せぬ
型が混入しても落ちないこと、十分な履歴があれば期待値に近い RSI を返すことを
回帰として固定する。
"""
from __future__ import annotations

from collections import deque

import pytest

from leverage_survival_lab.trading.bot import AITrader, BotConfig


def _trader(period: int = 14) -> AITrader:
    return AITrader(BotConfig(strategy="rsi", rsi_period=period))


def test_rsi_returns_none_when_history_too_short() -> None:
    t = _trader(period=14)
    for px in [100.0] * 10:
        t.minute_closes.append(px)
    assert t._rsi() is None


def test_rsi_monotonic_uptrend_close_to_100() -> None:
    t = _trader(period=14)
    for px in [100.0 + i for i in range(30)]:
        t.minute_closes.append(px)
    rsi = t._rsi()
    assert rsi is not None
    assert rsi == 100.0  # 全部 gain → avg_loss=0 → 100


def test_rsi_monotonic_downtrend_close_to_0() -> None:
    t = _trader(period=14)
    for px in [200.0 - i for i in range(30)]:
        t.minute_closes.append(px)
    rsi = t._rsi()
    assert rsi is not None
    assert rsi < 5.0


def test_rsi_choppy_neutral_around_50() -> None:
    t = _trader(period=14)
    base = 100.0
    for i in range(40):
        base += 1.0 if i % 2 == 0 else -1.0
        t.minute_closes.append(base)
    rsi = t._rsi()
    assert rsi is not None
    assert 30 < rsi < 70


def test_rsi_does_not_crash_on_polluted_deque() -> None:
    """deque に str/None 等が混入しても落ちずに None を返す or 数値を返す。

    これがランタイムで起きていた可能性を防御する。
    """
    t = _trader(period=14)
    # 全部数値以外 → None
    t.minute_closes = deque([None, "x", object()], maxlen=200)  # type: ignore[arg-type]
    assert t._rsi() is None
    # 一部だけ数値 + 残りはゴミ → 数値が period+1 未満なら None
    t.minute_closes = deque([1.0, 2.0, "x", None], maxlen=200)  # type: ignore[arg-type]
    assert t._rsi() is None


def test_rsi_handles_int_values() -> None:
    """deque に int が紛れても float と同様に扱える。"""
    t = _trader(period=14)
    for px in range(100, 130):  # int の連続上昇
        t.minute_closes.append(px)  # type: ignore[arg-type]
    rsi = t._rsi()
    assert rsi == 100.0


@pytest.mark.parametrize("period", [7, 14, 21])
def test_rsi_in_valid_range_for_random_walk(period: int) -> None:
    import numpy as np

    rng = np.random.default_rng(42)
    t = _trader(period=period)
    px = 100.0
    for _ in range(period * 3):
        px *= 1.0 + rng.normal(0, 0.005)
        t.minute_closes.append(px)
    rsi = t._rsi()
    assert rsi is not None
    assert 0.0 <= rsi <= 100.0
