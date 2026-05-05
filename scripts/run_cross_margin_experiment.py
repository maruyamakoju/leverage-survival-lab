"""Cross margin engine を使った実験 — Isolated との対比。

簡略な設計:
- 各 30日窓で、ランダム戦略を 5 銘柄(=同じ 1 銘柄を seed 違いで 5 サブストラテジ)
  に展開し、CrossMarginEngine に複数ポジション投入
- 各サブの risk_fraction は 0.10 (合計 50%)
- レバ別に 30日生存率を計測

Isolated と比較するため、同じシード・同じ戦略・同じレバで Isolated 実装も走らせる。
"""
from __future__ import annotations

import argparse

import numpy as np
import pandas as pd
from rich.console import Console

from leverage_survival_lab.analysis.stats import wilson_ci
from leverage_survival_lab.engine.cross_margin import CrossMarginEngine, _pid
from leverage_survival_lab.engine.leverage import FeeModel, Side
from leverage_survival_lab.strategies import RandomStrategy


def run_cross_window(df: pd.DataFrame, *, leverage: float, seed: int,
                      n_subs: int = 5, rf_per_sub: float = 0.10) -> dict:
    """1 つの 30日窓で cross margin を回す。"""
    rng = np.random.default_rng(seed)
    eng = CrossMarginEngine(initial_equity=1_000_000.0, fee=FeeModel())

    sigs: list[pd.Series] = [
        RandomStrategy(p_long=0.05, p_short=0.05, seed=int(rng.integers(0, 10**9))).generate(df)
        for _ in range(n_subs)
    ]

    opens = df["open"].to_numpy()
    highs = df["high"].to_numpy()
    lows = df["low"].to_numpy()
    closes = df["close"].to_numpy()
    sigs_arr = [s.to_numpy() for s in sigs]

    n = len(df)
    eq_curve = np.empty(n)

    for i in range(n):
        # アカウントレベル清算判定
        marks = {_pid(p): closes[i] for p in eng.positions}
        eng.step_check_account_liquidation(marks)

        # 各サブのシグナルに従って open / close
        for k, sig in enumerate(sigs_arr):
            # サブ k のポジを探す(open_bar が k 由来)。簡略化: ポジ数で識別。
            # ここでは「各サブが1ポジ」前提で、id でも構わないが簡略化
            pass

        # シンプル化: 各バーで対象サブのシグナルが立てば、その方向で open
        # クローズ条件: 次のシグナルで反対方向 / 5 バー保有 / SL -2%
        # 上記は厳密実装でないが、Isolated との対比のための smoke
        for k, sig in enumerate(sigs_arr):
            if i + 1 >= n:
                break
            if sig[i] != 0 and len(eng.positions) < n_subs:
                target = Side.LONG if sig[i] > 0 else Side.SHORT
                eng.open(side=target, price=float(opens[i + 1]), leverage=leverage,
                         risk_fraction=rf_per_sub, bar=i + 1)

        # 5 バー以上経過したポジを decay close
        for p in list(eng.positions):
            if i - p.open_bar >= 24:
                eng.close(p, price=closes[i])

        # equity 記録(unrealized 込み)
        unr = sum(p.unrealized_pnl(closes[i]) for p in eng.positions)
        eq_curve[i] = eng.equity + unr

        if eng.is_bust(0.10):
            for p in list(eng.positions):
                eng.close(p, price=closes[i])
            eq_curve[i:] = eng.equity
            break

    return {
        "leverage": leverage, "seed": seed,
        "final_equity": float(eq_curve[-1]),
        "is_bust": eng.is_bust(0.10),
        "n_liquidations": eng.n_liquidations,
    }


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p.add_argument("--n-windows", type=int, default=100)
    p.add_argument("--leverages", default="2,5,10,25,50,100")
    p.add_argument("--seed", type=int, default=42)
    args = p.parse_args()

    console = Console()
    df = pd.read_parquet(args.data)
    rng = np.random.default_rng(args.seed)
    starts = sorted({int(x) for x in rng.integers(0, len(df) - 24*30, size=args.n_windows)})
    levs = [float(x) for x in args.leverages.split(",")]

    console.print("=== Cross margin (5 random sub-strategies, rf=0.10 each) ===")
    rows = []
    for L in levs:
        finals = []
        for s in starts:
            sub = df.iloc[s : s + 24*30]
            r = run_cross_window(sub, leverage=L, seed=s)
            finals.append(r["final_equity"])
        finals = np.array(finals)
        successes = int((finals >= 100_000).sum())
        ci = wilson_ci(successes, len(finals))
        console.print(f"  {int(L)}x  N={len(finals)}  survival={ci.p*100:5.2f}%  CI=[{ci.lo*100:.2f}%, {ci.hi*100:.2f}%]")
        rows.append({"leverage": L, "n": len(finals), "survival": ci.p, "ci_lo": ci.lo, "ci_hi": ci.hi})

    out = pd.DataFrame(rows)
    out.to_parquet("results/cross_margin_summary.parquet", compression="zstd")
    console.print(f"\nsaved: results/cross_margin_summary.parquet")


if __name__ == "__main__":
    main()
