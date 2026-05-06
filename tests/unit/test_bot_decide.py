"""bot._decide() の回帰テスト。

V3.8 ライブ走行(tick 67717、19:39:53 UTC)で `'float' object is not subscriptable`
の TypeError が _decide() で発生した。stack trace なしでは特定困難だったため、
以下を防御として固定する:

1. 通常 state(ノーポジ・建玉中)で _decide が落ちないこと
2. state["position"] が予期せぬ型(float, str, ...)のときも DECIDE_ERROR は
   呼び出し側で catch されるが、_decide 自体は明確に AttributeError or TypeError
   を上げて握りつぶさない(後段の except で捕捉してログするのが正しい挙動)
3. cooldown / RSI エントリ条件の境界が壊れない
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from leverage_survival_lab.trading.bot import AITrader, BotConfig


def _trader(strategy: str = "rsi") -> AITrader:
    t = AITrader(BotConfig(strategy=strategy, rsi_period=14))
    # 中立の RSI(~50)を作るために交互に上下させる
    base = 100.0
    for i in range(40):
        base += 0.5 if i % 2 == 0 else -0.5
        t.minute_closes.append(base)
    t.now_ts = datetime.now(UTC)
    return t


def _state(position=None, price: float = 100.0,
           equity: float = 1_000_000.0) -> dict:
    return {
        "ts": datetime.now(UTC).isoformat(),
        "price": price,
        "position": position,
        "equity": equity,
        "total_value": equity,
        "initial_equity": equity,
    }


# ---------- ノーポジでの正常系 ----------

def test_decide_no_position_neutral_rsi_returns_none() -> None:
    t = _trader()
    assert t._decide(_state()) is None


def test_decide_no_position_oversold_returns_long() -> None:
    t = AITrader(BotConfig(strategy="rsi", rsi_period=14))
    # 強い下落 → 強い oversold
    for px in (100.0 - i for i in range(30)):
        t.minute_closes.append(px)
    t.now_ts = datetime.now(UTC)
    decision = t._decide(_state())
    assert decision is not None
    assert decision[0] == "long"


def test_decide_no_position_overbought_returns_short() -> None:
    t = AITrader(BotConfig(strategy="rsi", rsi_period=14))
    for px in (100.0 + i for i in range(30)):
        t.minute_closes.append(px)
    t.now_ts = datetime.now(UTC)
    decision = t._decide(_state())
    assert decision is not None
    assert decision[0] == "short"


def test_decide_respects_tick_cooldown() -> None:
    t = _trader()
    t.last_trade_tick = t.tick_idx  # 直前にトレードした
    # tick_idx と last_trade_tick が同じなので cooldown_ticks (10) 以内
    assert t._decide(_state()) is None


def test_decide_respects_seconds_cooldown() -> None:
    t = _trader()
    t.last_trade_tick = t.tick_idx - 100  # tick cooldown は明けてる
    t.last_trade_ts = t.now_ts  # 秒 cooldown はちょうど
    # cooldown_seconds=30 以内なのでエントリしない
    assert t._decide(_state()) is None


# ---------- 建玉中の挙動 ----------

def test_decide_in_position_no_close_when_within_hold_limit() -> None:
    t = _trader()
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=30)
    # 30 秒 hold は hold_max_seconds=600 未満
    pos = {"side": "long", "entry_price": 100.0, "qty": 1.0}
    assert t._decide(_state(position=pos)) is None


def test_decide_in_position_closes_when_hold_seconds_exceeded() -> None:
    t = _trader()
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=700)
    pos = {"side": "long", "entry_price": 100.0, "qty": 1.0}
    decision = t._decide(_state(position=pos))
    assert decision is not None
    assert decision[0] == "close"
    assert "秒" in decision[1]  # 秒ベースの理由


def test_decide_in_position_long_early_exit_when_rsi_recovered() -> None:
    t = AITrader(BotConfig(strategy="rsi"))
    # RSI が 45 以上になる十分な上昇を持たせる
    for px in (100.0 + i for i in range(30)):
        t.minute_closes.append(px)
    t.now_ts = datetime.now(UTC)
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=120)
    pos = {"side": "long", "entry_price": 100.0, "qty": 1.0}
    decision = t._decide(_state(position=pos))
    assert decision is not None
    assert decision[0] == "close"
    assert "RSI" in decision[1]


def test_decide_in_position_held_too_short_no_early_exit() -> None:
    t = AITrader(BotConfig(strategy="rsi"))
    for px in (100.0 + i for i in range(30)):
        t.minute_closes.append(px)
    t.now_ts = datetime.now(UTC)
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=30)  # 60秒未満
    pos = {"side": "long", "entry_price": 100.0, "qty": 1.0}
    # 60秒未満は早期利確しない設計
    assert t._decide(_state(position=pos)) is None


# ---------- 防御: state[position] の型ゆらぎ ----------

def test_decide_position_dict_without_side_key_does_not_crash_until_rsi_check() -> None:
    """state[position] が辞書だが side キー欠落でも、hold 時間チェックまでは通る。"""
    t = _trader()
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=30)  # 60秒未満
    pos = {}  # side キー欠落
    # RSI early exit には到達しないので落ちない
    assert t._decide(_state(position=pos)) is None


def test_decide_position_with_missing_side_at_early_exit() -> None:
    """side キー欠落時、.get('side') は None を返すので side==short/long にならず通過。"""
    t = AITrader(BotConfig(strategy="rsi"))
    for px in (100.0 + i for i in range(30)):
        t.minute_closes.append(px)
    t.now_ts = datetime.now(UTC)
    t.position_opened_at = t.tick_idx - 5
    t.position_opened_ts = t.now_ts - timedelta(seconds=120)
    pos = {}
    # side が None → どちらの早期利確条件にもマッチしないので None 返す
    assert t._decide(_state(position=pos)) is None


# ---------- 防御: 戦略モード切替 ----------

def test_decide_zscore_short_history_returns_none() -> None:
    t = AITrader(BotConfig(strategy="zscore", history_size=60))
    t.now_ts = datetime.now(UTC)
    # prices が history_size//2 未満
    for px in (100.0 + i for i in range(10)):
        t.prices.append(px)
    assert t._decide(_state()) is None


def test_decide_momentum_warmup_blocks_entry() -> None:
    """momentum mode は live_candle_count が breakout_window+1 未満なら判定保留。"""
    t = AITrader(BotConfig(strategy="momentum", breakout_window=30))
    t.now_ts = datetime.now(UTC)
    for px in (100.0 + i for i in range(50)):
        t.minute_closes.append(px)
    t.live_candle_count = 5  # warmup 不足
    assert t._decide(_state()) is None


def test_decide_trend_sma_returns_long_on_filtered_uptrend() -> None:
    t = AITrader(BotConfig(strategy="trend_sma", trend_fast=20, trend_slow=50, trend_window=200))
    t.now_ts = datetime.now(UTC)
    for px in [100.0] * 150 + [102.0] * 30 + [110.0] * 20:
        t.minute_closes.append(px)

    decision = t._decide(_state(price=110.0))
    assert decision is not None
    assert decision[0] == "long"


def test_decide_trend_sma_returns_short_on_filtered_downtrend() -> None:
    t = AITrader(BotConfig(strategy="trend_sma", trend_fast=20, trend_slow=50, trend_window=200))
    t.now_ts = datetime.now(UTC)
    for px in [100.0] * 150 + [98.0] * 30 + [90.0] * 20:
        t.minute_closes.append(px)

    decision = t._decide(_state(price=90.0))
    assert decision is not None
    assert decision[0] == "short"


def test_decide_trend_sma_closes_long_when_signal_is_lost() -> None:
    t = AITrader(BotConfig(
        strategy="trend_sma",
        trend_fast=20,
        trend_slow=50,
        trend_window=200,
        hold_max_seconds=24 * 60 * 60,
    ))
    t.now_ts = datetime.now(UTC)
    t.position_opened_at = t.tick_idx - 10
    t.position_opened_ts = t.now_ts - timedelta(seconds=120)
    for px in [100.0] * 200:
        t.minute_closes.append(px)

    decision = t._decide(_state(position={"side": "long"}, price=100.0))
    assert decision is not None
    assert decision[0] == "close"
    assert "trend_sma exit" in decision[1]


def test_decide_trend_sma_blocks_same_signal_reentry_after_external_close() -> None:
    t = AITrader(BotConfig(strategy="trend_sma", trend_fast=20, trend_slow=50, trend_window=200))
    t.now_ts = datetime.now(UTC)
    for px in [100.0] * 150 + [102.0] * 30 + [110.0] * 20:
        t.minute_closes.append(px)
    t._blocked_trend_signal = 1

    assert t._decide(_state(price=110.0)) is None


def test_decide_trend_sma_allows_reentry_after_signal_changes() -> None:
    t = AITrader(BotConfig(strategy="trend_sma", trend_fast=20, trend_slow=50, trend_window=200))
    t.now_ts = datetime.now(UTC)
    for px in [100.0] * 150 + [98.0] * 30 + [90.0] * 20:
        t.minute_closes.append(px)
    t._blocked_trend_signal = 1

    decision = t._decide(_state(price=90.0))
    assert decision is not None
    assert decision[0] == "short"


# ---------- スモーク: 何度連続で呼んでも落ちない ----------

def test_decide_smoke_repeated_calls_no_crash() -> None:
    """ノーポジ → ポジ建玉 → 解消 を繰り返しても _decide が崩れないこと。
    V3.8 のような長時間ライブで散発的に発生したエラーを早期検知する目的。"""
    t = _trader()
    pos = {"side": "long", "entry_price": 100.0, "qty": 1.0}
    for _ in range(50):
        t._decide(_state())
        t._decide(_state(position=pos))
        t._decide(_state(position=None))
