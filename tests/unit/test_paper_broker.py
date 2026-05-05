"""ペーパートレード broker のテスト。"""
from __future__ import annotations

from leverage_survival_lab.data.synthetic import gbm_ohlcv
from leverage_survival_lab.trading.feeds import replay_feed
from leverage_survival_lab.trading.paper import PaperBroker


def test_broker_long_then_close_at_higher_price() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    msg = b.long(size_pct=0.5, leverage=10)
    assert "opened LONG" in msg
    # tick to higher price
    b.tick(price=110.0, high=110.5, low=99.0)
    msg = b.close()
    assert "closed LONG" in msg
    # +10% × 10 leverage on 50% size = +50% on equity (minus fees)
    assert b.equity > 1_400_000


def test_broker_short_then_close_at_lower_price() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    b.short(size_pct=0.5, leverage=10)
    b.tick(price=90.0, high=101.0, low=89.0)
    msg = b.close()
    assert "closed SHORT" in msg
    assert b.equity > 1_400_000


def test_stop_loss_triggers_on_intra_bar_low() -> None:
    b = PaperBroker(initial_equity=1_000_000, sl_pct=-0.02)
    b.last_price = 100.0
    b.long(size_pct=1.0, leverage=10)
    # bar low = 97 (3% below entry, > 2% stop)
    msgs = b.tick(price=98.0, high=100.5, low=97.0)
    assert any("SL hit" in m for m in msgs)
    assert b.position is None


def test_liquidation_at_100x_long() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    # 100x at 0.2% size = 200k notional, mm=0.005 < 1/100=0.01 → OK
    msg = b.long(size_pct=0.002, leverage=100)
    assert "opened LONG" in msg
    msgs = b.tick(price=99.4, high=100.0, low=99.0)
    assert any("LIQUIDATED" in m for m in msgs)
    assert b.position is None


def test_paper_broker_rejects_unrealistic_combo() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    # 100x × 100% size = 100M notional → mm tier 0.10 >= 1/100
    msg = b.long(size_pct=1.0, leverage=100)
    assert "REJECTED" in msg
    assert b.position is None  # 開いていない


def test_double_open_returns_error_string() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    b.long()
    msg = b.long()
    assert "already in position" in msg


def test_replay_feed_advances_correctly() -> None:
    df = gbm_ohlcv(n_bars=10, seed=0)
    feed = list(replay_feed(df))
    assert len(feed) == 10
    # 全要素に price/high/low/ts が含まれる
    assert all({"price", "high", "low", "ts"} <= set(t.keys()) for t in feed)


def test_to_dict_persists_state() -> None:
    b = PaperBroker(initial_equity=1_000_000)
    b.last_price = 100.0
    b.long()
    b.tick(price=110.0, high=110.0, low=99.0)
    b.close()
    d = b.to_dict()
    assert d["n_trades"] == 2  # open + close
    assert d["equity"] > 0
    assert "trades" in d and len(d["trades"]) == 2
