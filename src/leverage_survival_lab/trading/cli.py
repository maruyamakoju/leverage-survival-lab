"""ペーパートレード対話 CLI — `lsl-trade` エントリポイント。

主要コマンド:
  long [size%] [lev]     - ロングを開く(例: long 50 25 = 50%資金 × 25倍レバ)
  short [size%] [lev]    - ショートを開く
  close                  - 現在のポジションを成行決済
  sl <pct>               - SL を 価格逆行 % で設定 (例: sl 2 で -2%)
  tp <pct>               - TP を順行 % で設定 (例: tp 5 で +5%)
  lev <x>                - 既定レバを変更
  size <pct>             - 既定サイズ% を変更
  next [n]               - n バー進める(default 1)
  auto <n>               - 1 バーごとに 0.5秒待つ自動再生 (n バー)
  status / s             - 現状サマリ表示
  trades                 - 取引履歴
  chart                  - 簡易 ASCII chart
  save <path>            - セッション保存
  help / ?
  quit / q
"""
from __future__ import annotations

import argparse
import shlex
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pandas as pd
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .feeds import live_binance_feed, random_window_replay, replay_feed
from .paper import PaperBroker

console = Console()


HELP = """\
[bold cyan]Commands[/bold cyan]
  [yellow]long[/yellow] [size%] [lev]    open long  (default: 100% size, 10x lev)
  [yellow]short[/yellow] [size%] [lev]   open short
  [yellow]close[/yellow]                 close current position at market
  [yellow]sl[/yellow] <pct>              set stop-loss (e.g. 'sl 2' = -2%)
  [yellow]tp[/yellow] <pct>              set take-profit
  [yellow]lev[/yellow] <x>               set default leverage
  [yellow]size[/yellow] <pct>            set default size (% of equity)
  [yellow]next[/yellow] [n]              advance n ticks (default 1)
  [yellow]auto[/yellow] <n> [delay_ms]   auto-advance n ticks (delay default 200ms)
  [yellow]status[/yellow] / s            show summary
  [yellow]trades[/yellow]                list recent trades
  [yellow]chart[/yellow]                 ASCII price + equity chart
  [yellow]save[/yellow] <path>           save session to JSON
  [yellow]help[/yellow] / ?              this help
  [yellow]quit[/yellow] / q              exit
"""


def render_status(broker: PaperBroker, last_tick: dict[str, Any] | None) -> Panel:
    pos = broker.position
    pnl_pct = (broker.total_value / broker.initial_equity - 1.0) * 100

    pos_text = "[grey]flat[/grey]"
    if pos is not None:
        side_color = "green" if pos.side.value == "long" else "red"
        unr = broker.unrealized_pnl
        unr_color = "green" if unr >= 0 else "red"
        liq_dist = abs(broker.last_price - pos.liq_price) / broker.last_price * 100 if broker.last_price else 0
        pos_text = (f"[{side_color}]{pos.side.value.upper()}[/{side_color}] "
                    f"qty={pos.qty:.6f} @ {pos.entry:.2f}  "
                    f"lev={pos.leverage:.0f}x  "
                    f"liq={pos.liq_price:.2f} ({liq_dist:.2f}% away)  "
                    f"unrealized=[{unr_color}]{unr:+.2f}[/{unr_color}]")

    sl_text = f"{broker.sl_pct*100:.1f}%" if broker.sl_pct else "—"
    tp_text = f"{broker.tp_pct*100:.1f}%" if broker.tp_pct else "—"
    pnl_color = "green" if pnl_pct >= 0 else "red"
    ts_text = last_tick["ts"] if last_tick else "—"

    body = (
        f"[bold]Price:[/bold] {broker.last_price:>12,.2f}    [grey]{ts_text}[/grey]\n"
        f"[bold]Equity:[/bold] {broker.equity:>11,.2f}  +unr {broker.unrealized_pnl:+,.2f}  "
        f"= {broker.total_value:>11,.2f}  [{pnl_color}]({pnl_pct:+.2f}%)[/{pnl_color}]\n"
        f"[bold]Position:[/bold] {pos_text}\n"
        f"[bold]SL/TP:[/bold] sl={sl_text}  tp={tp_text}  "
        f"default lev={broker.default_leverage}x size={broker.default_size_pct*100:.0f}%  "
        f"liquidations={broker.engine.n_liquidations}"
    )
    return Panel(body, title="Paper Account", border_style="cyan")


def render_chart(broker: PaperBroker, n: int = 60) -> str:
    """簡易 ASCII chart: 直近 n tick の price と equity を表示。"""
    if not broker.ticks:
        return "[grey]no ticks yet[/grey]"
    sub = broker.ticks[-n:]
    prices = [t.price for t in sub]
    equities = [t.equity + t.unrealized_pnl for t in sub]

    def line(values: list[float], height: int = 8) -> list[str]:
        if not values:
            return ["(empty)"]
        lo, hi = min(values), max(values)
        rng = hi - lo or 1.0
        rows = []
        for r in range(height, 0, -1):
            row = []
            for v in values:
                level = (v - lo) / rng * height
                row.append("█" if level >= r else "░" if level >= r - 0.5 else " ")
            rows.append("".join(row) + f"  {hi if r==height else (lo if r==1 else '')}")
        return rows

    out = ["[bold]Price[/bold]:"]
    out += line(prices)
    out.append(f"  range: {min(prices):,.2f} .. {max(prices):,.2f}")
    out.append("")
    out.append("[bold]Equity[/bold]:")
    out += line(equities)
    out.append(f"  range: {min(equities):,.2f} .. {max(equities):,.2f}")
    return "\n".join(out)


def parse_command(line: str) -> tuple[str, list[str]]:
    parts = shlex.split(line.strip())
    if not parts:
        return "", []
    return parts[0].lower(), parts[1:]


def repl(broker: PaperBroker, feed: Iterator[dict[str, Any]]) -> None:
    last_tick: dict[str, Any] | None = None
    # 初回 tick で価格を取得
    try:
        last_tick = next(feed)
        broker.tick(**last_tick)
    except StopIteration:
        console.print("[red]feed exhausted before first tick[/red]")
        return

    console.print(Panel(HELP, title="Welcome to Paper Trading", border_style="green"))
    console.print(render_status(broker, last_tick))

    while True:
        try:
            line = console.input("[bold cyan]> [/bold cyan]")
        except (EOFError, KeyboardInterrupt):
            console.print("\n[yellow]bye[/yellow]")
            break

        cmd, args = parse_command(line)
        if not cmd:
            continue

        try:
            if cmd in ("quit", "q", "exit"):
                console.print("[yellow]bye[/yellow]")
                break

            elif cmd in ("help", "?"):
                console.print(Panel(HELP, border_style="green"))

            elif cmd in ("status", "s", "info", "i"):
                console.print(render_status(broker, last_tick))

            elif cmd == "long":
                size = float(args[0]) / 100 if len(args) >= 1 else None
                lev = float(args[1]) if len(args) >= 2 else None
                msg = broker.long(size_pct=size, leverage=lev)
                console.print(f"[green]{msg}[/green]")

            elif cmd == "short":
                size = float(args[0]) / 100 if len(args) >= 1 else None
                lev = float(args[1]) if len(args) >= 2 else None
                msg = broker.short(size_pct=size, leverage=lev)
                console.print(f"[red]{msg}[/red]")

            elif cmd == "close":
                msg = broker.close()
                console.print(f"[white]{msg}[/white]")

            elif cmd == "sl":
                pct = float(args[0]) / 100 if args else None
                console.print(broker.set_sl(pct))

            elif cmd == "tp":
                pct = float(args[0]) / 100 if args else None
                console.print(broker.set_tp(pct))

            elif cmd == "lev":
                console.print(broker.set_leverage(float(args[0])))

            elif cmd == "size":
                console.print(broker.set_size(float(args[0]) / 100))

            elif cmd in ("next", "n"):
                n = int(args[0]) if args else 1
                for _ in range(n):
                    try:
                        last_tick = next(feed)
                    except StopIteration:
                        console.print("[yellow]feed exhausted[/yellow]")
                        break
                    msgs = broker.tick(**last_tick)
                    for m in msgs:
                        console.print(f"  [magenta]{m}[/magenta]")
                console.print(render_status(broker, last_tick))

            elif cmd == "auto":
                n = int(args[0]) if args else 60
                delay = float(args[1]) / 1000 if len(args) >= 2 else 0.2
                console.print(f"[grey]auto-advancing {n} ticks every {delay*1000:.0f}ms (Ctrl-C to stop)[/grey]")
                try:
                    for _ in range(n):
                        last_tick = next(feed)
                        msgs = broker.tick(**last_tick)
                        for m in msgs:
                            console.print(f"  [magenta]{m}[/magenta]")
                        # ライブ更新風に短い status
                        pnl_pct = (broker.total_value / broker.initial_equity - 1.0) * 100
                        console.print(f"  [dim]{last_tick['ts']}[/dim]  "
                                      f"px={last_tick['price']:>10,.2f}  "
                                      f"eq={broker.total_value:>11,.2f}  ({pnl_pct:+.2f}%)")
                        time.sleep(delay)
                except (StopIteration, KeyboardInterrupt):
                    pass
                console.print(render_status(broker, last_tick))

            elif cmd == "trades":
                if not broker.trades:
                    console.print("[grey]no trades yet[/grey]")
                else:
                    table = Table(title=f"Recent trades (last 20 of {len(broker.trades)})")
                    table.add_column("ts")
                    table.add_column("action")
                    table.add_column("price")
                    table.add_column("qty")
                    table.add_column("lev")
                    table.add_column("pnl")
                    for t in broker.trades[-20:]:
                        pnl_str = f"{t.pnl:+,.2f}" if t.pnl is not None else "—"
                        table.add_row(t.ts.split("T")[1][:8], t.action,
                                      f"{t.price:.2f}", f"{t.qty:.6f}",
                                      f"{t.leverage:.0f}x", pnl_str)
                    console.print(table)

            elif cmd == "chart":
                console.print(Panel(Text.from_markup(render_chart(broker)), border_style="white"))

            elif cmd == "save":
                path = Path(args[0]) if args else Path("results/paper_session.json")
                broker.save(path)
                console.print(f"[green]saved to {path}[/green]")

            else:
                console.print(f"[red]unknown command: {cmd}[/red]  (try 'help')")

        except (ValueError, IndexError) as e:
            console.print(f"[red]bad args: {e}[/red]")


def main() -> None:
    p = argparse.ArgumentParser(description="ペーパートレード CLI(仮想金で BTC をバンバン触る)")
    sub = p.add_subparsers(dest="mode", required=True)

    p_replay = sub.add_parser("replay", help="過去データを早送り再生")
    p_replay.add_argument("--data", default="data/raw/binance_BTCUSDT_1h.parquet")
    p_replay.add_argument("--start", default=None, help="ISO 日付 (例: 2024-01-01)")
    p_replay.add_argument("--end", default=None)
    p_replay.add_argument("--random-window", type=int, default=None,
                          help="ランダムに N バー切り出して再生")
    p_replay.add_argument("--seed", type=int, default=None)

    p_live = sub.add_parser("live", help="Binance 実時間価格(仮想金)")
    p_live.add_argument("--symbol", default="BTC/USDT")
    p_live.add_argument("--poll", type=float, default=5.0, help="polling 秒")

    for sp in (p_replay, p_live):
        sp.add_argument("--equity", type=float, default=1_000_000.0)
        sp.add_argument("--leverage", type=float, default=10.0)
        sp.add_argument("--size", type=float, default=1.0, help="既定サイズ (0..1)")

    args = p.parse_args()

    broker = PaperBroker(initial_equity=args.equity, default_leverage=args.leverage,
                        default_size_pct=args.size)

    if args.mode == "replay":
        df = pd.read_parquet(args.data)
        if args.random_window:
            feed = random_window_replay(df, window_bars=args.random_window, seed=args.seed)
        else:
            feed = replay_feed(df, start=args.start, end=args.end)
    else:
        console.print("[yellow]live mode: polling Binance (Ctrl-C to stop)[/yellow]")
        feed = live_binance_feed(symbol=args.symbol, poll_seconds=args.poll)

    repl(broker, feed)


if __name__ == "__main__":
    main()
