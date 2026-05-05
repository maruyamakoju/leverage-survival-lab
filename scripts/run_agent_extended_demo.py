"""より多様な investigation を回す extended agent demo。

各サイクルで:
- 仮説を選ぶ(初期 4 + バリエーション)
- パラメータを変える(N, leverage range, asset, etc.)
- 実験 → insight 抽出 → 履歴に追加

このスクリプトは subprocess で投げ直すラッパーから呼ぶ前提でも、自走でも動く。
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

INVESTIGATIONS: list[dict] = [
    # 初期 4 仮説 (各 50 windows)
    {"hypothesis": "H1", "n_windows": 50, "asset": "BTC", "rationale": "100x の生存率 CI 上限を計測"},
    {"hypothesis": "H2", "n_windows": 50, "asset": "BTC", "rationale": "中レバ域で内点解があるか"},
    {"hypothesis": "H3", "n_windows": 50, "asset": "BTC", "rationale": "戦略のエッジ閾値"},
    {"hypothesis": "H4", "n_windows": 50, "asset": "BTC", "rationale": "高レバで戦略差が消えるか"},
    # 拡張 investigation
    {"hypothesis": "H1", "n_windows": 100, "asset": "ETH", "rationale": "H1 の ETH での再現性"},
    {"hypothesis": "H1", "n_windows": 100, "asset": "SOL", "rationale": "H1 の SOL での再現性"},
    {"hypothesis": "H1", "n_windows": 100, "asset": "BTC", "rationale": "BTC で N を増やして CI を狭める"},
    {"hypothesis": "H4", "n_windows": 100, "asset": "BTC", "rationale": "戦略間差を高 N で検定"},
    {"hypothesis": "H2", "n_windows": 100, "asset": "BTC", "rationale": "内点解の出現頻度を計測"},
    {"hypothesis": "H3", "n_windows": 100, "asset": "BTC", "rationale": "trend filter のエッジ閾値"},
]


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--out-log", default="results/agent_log.jsonl")
    p.add_argument("--start-from", type=int, default=0)
    p.add_argument("--limit", type=int, default=10)
    args = p.parse_args()

    py = sys.executable
    out_path = Path(args.out_log)
    investigations = INVESTIGATIONS[args.start_from : args.start_from + args.limit]

    h_index = {"H1": 0, "H2": 1, "H3": 2, "H4": 3}
    for i, inv in enumerate(investigations):
        cycle_no = args.start_from + i + 1
        seed = 1000 + cycle_no * 13

        data_path = f"data/raw/binance_{inv['asset']}USDT_1h.parquet"
        if not Path(data_path).exists():
            print(f"[cycle {cycle_no}] skip: missing {data_path}")
            continue

        cmd = [py, "-X", "faulthandler", "-W", "ignore::RuntimeWarning",
               "scripts/run_agent_cycle_isolated.py",
               "--data", data_path,
               "--hypothesis-idx", str(h_index[inv["hypothesis"]]),
               "--seed", str(seed),
               "--n-windows", str(inv["n_windows"]),
               "--out-log", str(out_path)]
        # 最大 3 回試行
        ok = False
        for attempt in range(3):
            res = subprocess.run(cmd, capture_output=False)
            if res.returncode == 0:
                ok = True
                break
            cmd[-3] = str(seed + 1000 * (attempt + 1))  # next seed
        if not ok:
            # 失敗を log にも残す
            with out_path.open("a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "cycle": cycle_no, "hypothesis": inv["hypothesis"],
                    "asset": inv["asset"], "n_windows": inv["n_windows"],
                    "rationale": inv["rationale"],
                    "status": "FAILED after 3 attempts (Windows native crash)",
                }, ensure_ascii=False) + "\n")
        print(f"[cycle {cycle_no}/{len(investigations)+args.start_from}] {inv['hypothesis']} {inv['asset']} n={inv['n_windows']} {'OK' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
