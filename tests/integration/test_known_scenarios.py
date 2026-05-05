"""既知の暗号クラッシュ期間で、レバ100倍が想定通り清算されることを確認する結合テスト。

実データが `data/raw/binance_BTCUSDT_1h.parquet` に存在することを前提とする。
データがない環境では skip される。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from leverage_survival_lab.backtest import BacktestConfig, run_backtest
from leverage_survival_lab.data.fixtures import KNOWN_SCENARIOS, slice_scenario
from leverage_survival_lab.strategies import RandomStrategy

DATA = Path("data/raw/binance_BTCUSDT_1h.parquet")


@pytest.fixture(scope="module")
def btc_1h() -> pd.DataFrame:
    if not DATA.exists():
        pytest.skip(f"missing {DATA} — run `python -m leverage_survival_lab.data.fetch ohlcv ...`")
    return pd.read_parquet(DATA)


@pytest.mark.integration
@pytest.mark.parametrize("scenario", [s[0] for s in KNOWN_SCENARIOS if s[0] != "bull_run_2021"])
def test_high_leverage_busts_in_crashes(btc_1h: pd.DataFrame, scenario: str) -> None:
    """既知のクラッシュ期間で 100x レバが破産する(直感的サニティチェック)。"""
    sub = slice_scenario(btc_1h, scenario)
    if sub.empty:
        pytest.skip(f"no data for {scenario}")

    sig = RandomStrategy(p_long=0.10, p_short=0.0, seed=0).generate(sub)  # ロング寄り
    result = run_backtest(sub, sig, BacktestConfig(leverage=100.0, stop_loss=None,
                                                    risk_fraction=1.0))
    # 100倍ロングがクラッシュ期間を生き延びるはずがない
    assert result.is_bust, f"100x long should bust during {scenario}, got equity={result.final_equity}"
    assert result.n_liquidations >= 1


@pytest.mark.integration
def test_low_leverage_survives_bull_run(btc_1h: pd.DataFrame) -> None:
    """ブル期に 2x ロングが生存する(逆向きのサニティチェック)。"""
    sub = slice_scenario(btc_1h, "bull_run_2021")
    if sub.empty:
        pytest.skip("no data for bull_run_2021")
    sig = RandomStrategy(p_long=0.10, p_short=0.0, seed=0).generate(sub)
    result = run_backtest(sub, sig, BacktestConfig(leverage=2.0, stop_loss=-0.05,
                                                    risk_fraction=0.5))
    # 2x で半分しか張らなければブル期は概ね生き残る
    assert not result.is_bust, f"2x small-size long should survive bull run, equity={result.final_equity}"
