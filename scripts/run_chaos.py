from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from reliability_lab.chaos import load_queries, run_simulation
from reliability_lab.config import load_config


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/metrics.json")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--requests", type=int, default=None)
    args = parser.parse_args()
    config = load_config(args.config)
    if args.requests is not None:
        config.load_test.requests = args.requests
    metrics = run_simulation(config, load_queries(), seed=args.seed)
    metrics.write_json(args.out)
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
