"""ライブ実演ログ(ai_trader_*.log)から集計・図を生成。"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

DEMO_DIR = Path("results/live_demo")
FIG_DIR = Path("results/figures")
FIG_DIR.mkdir(parents=True, exist_ok=True)


import re
PNL_RE = re.compile(r"損益 ([+\-]?)\$?([\-]?[\d,]+\.\d+)")


def _extract_pnl(result_text: str) -> float | None:
    if not result_text:
        return None
    m = PNL_RE.search(result_text)
    if not m:
        return None
    sign, num = m.group(1), m.group(2)
    val = float(num.replace(",", ""))
    if sign == "-":
        val = -abs(val)
    return val


def parse_log(path: Path) -> tuple[list[dict], list[dict]]:
    """ログから (actions, heartbeats) を抽出。close の pnl は result 文字列から抽出。"""
    actions, heartbeats = [], []
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            a = rec.get("action")
            if a == "HEARTBEAT":
                heartbeats.append(rec)
            elif a in ("open_long", "open_short", "close", "STOP"):
                if a == "close" and "pnl" not in rec:
                    rec["pnl"] = _extract_pnl(rec.get("result", ""))
                actions.append(rec)
    return actions, heartbeats


def summarize(actions: list[dict], heartbeats: list[dict], label: str) -> dict:
    closes = [a for a in actions if a["action"] == "close" and a.get("result") and "ポジションがありません" not in a["result"]]
    opens = [a for a in actions if a["action"] in ("open_long", "open_short") and a.get("ok", False)]
    pnls = [c["pnl"] for c in closes if c.get("pnl") is not None]
    wins = sum(1 for p in pnls if p > 0)
    losses = sum(1 for p in pnls if p <= 0)
    cum_pnl = sum(pnls)
    rejected = [a for a in actions if a.get("ok") is False or "拒否" in str(a.get("result", "")) or "既にポジ" in str(a.get("result", ""))]

    if heartbeats:
        first_total = heartbeats[0].get("total", 1_000_000)
        last_total = heartbeats[-1].get("total", first_total)
        first_ts = heartbeats[0]["ts"]
        last_ts = heartbeats[-1]["ts"]
    else:
        first_total = last_total = 1_000_000
        first_ts = last_ts = ""

    return {
        "label": label,
        "n_open": len(opens),
        "n_close": len(closes),
        "n_rejected": len(rejected),
        "wins": wins,
        "losses": losses,
        "cum_pnl": cum_pnl,
        "win_rate": wins / len(pnls) if pnls else 0.0,
        "first_ts": first_ts,
        "last_ts": last_ts,
        "first_total": first_total,
        "last_total": last_total,
        "drawdown_pct": (last_total / 1_000_000 - 1) * 100,
        "pnls": pnls,
        "heartbeats": heartbeats,
    }


def main() -> None:
    v1 = parse_log(DEMO_DIR / "v1_25x_30sec.log")
    v2 = parse_log(DEMO_DIR / "v2_5x_3min.log")
    s1 = summarize(*v1, "V1: 25x × 20% × 300t hold")
    s2 = summarize(*v2, "V2: 5x × 30% × 1800t hold")

    print("=== V1 ===")
    print(f"  trades: open={s1['n_open']}, close={s1['n_close']}, rejected={s1['n_rejected']}")
    print(f"  win/loss: {s1['wins']}/{s1['losses']} (win rate: {s1['win_rate']*100:.1f}%)")
    print(f"  cum PnL: ${s1['cum_pnl']:+,.0f}")
    print(f"  total drawdown: {s1['drawdown_pct']:+.2f}%")
    print()
    print("=== V2 ===")
    print(f"  trades: open={s2['n_open']}, close={s2['n_close']}, rejected={s2['n_rejected']}")
    print(f"  win/loss: {s2['wins']}/{s2['losses']} (win rate: {s2['win_rate']*100:.1f}%)")
    print(f"  cum PnL: ${s2['cum_pnl']:+,.0f}")
    print(f"  total drawdown: {s2['drawdown_pct']:+.2f}%")

    # 図 1: equity curve(両方を時刻でアラインしてプロット)
    fig, ax = plt.subplots(figsize=(11, 5.5))
    for s, color in [(s1, "#da3633"), (s2, "#2ea043")]:
        if not s["heartbeats"]:
            continue
        from datetime import datetime
        ts0 = datetime.fromisoformat(s["heartbeats"][0]["ts"].replace("Z", "+00:00"))
        elapsed = [(datetime.fromisoformat(h["ts"].replace("Z", "+00:00")) - ts0).total_seconds() for h in s["heartbeats"]]
        totals = [h["total"] for h in s["heartbeats"]]
        ax.plot(elapsed, totals, color=color, lw=2, label=s["label"])

    ax.axhline(1_000_000, ls="--", color="black", alpha=0.4, lw=0.7)
    ax.axhline(700_000, ls="--", color="orange", alpha=0.4, lw=0.7, label="−30% line")
    ax.axhline(500_000, ls="--", color="red", alpha=0.4, lw=0.7, label="V2 STOP threshold (50%)")
    ax.set_xlabel("Elapsed seconds since bot start")
    ax.set_ylabel("Account total value (USD)")
    ax.set_title("Live AI Trader Demo — Equity Curve")
    ax.legend(loc="upper right")
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(FIG_DIR / "live_demo_equity.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    # 図 2: 取引別 PnL ヒストグラム(V1 vs V2)
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for ax, s, color in [(axes[0], s1, "#da3633"), (axes[1], s2, "#2ea043")]:
        if s["pnls"]:
            ax.hist(s["pnls"], bins=20, color=color, alpha=0.7, edgecolor="black")
            ax.axvline(0, color="black", lw=0.7)
            ax.axvline(np.mean(s["pnls"]), color="black", ls="--",
                       label=f"mean ${np.mean(s['pnls']):+,.0f}")
            ax.legend()
        ax.set_title(s["label"])
        ax.set_xlabel("Trade PnL (USD)")
        ax.set_ylabel("Count")
        ax.grid(alpha=0.3)
    fig.suptitle("Per-trade PnL distribution")
    fig.tight_layout()
    fig.savefig(FIG_DIR / "live_demo_pnl_hist.png", dpi=140, bbox_inches="tight")
    plt.close(fig)

    print(f"\nfigures saved to {FIG_DIR}")


if __name__ == "__main__":
    main()
