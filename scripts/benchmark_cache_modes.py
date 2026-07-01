from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from reliability_lab.chaos import clone_config, load_queries, run_simulation
from reliability_lab.config import load_config


def average(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def benchmark_mode(
    config_path: str,
    mode: str,
    requests: int,
    repeats: int,
    seed: int,
) -> dict[str, object]:
    base_config = load_config(config_path)
    queries = load_queries()
    runs: list[dict[str, object]] = []

    for offset in range(repeats):
        config = clone_config(base_config)
        config.load_test.requests = requests
        if mode == "no-cache":
            config.cache.enabled = False
        elif mode == "redis":
            config.cache.enabled = True
            config.cache.backend = "redis"
        else:
            config.cache.enabled = True
            config.cache.backend = "memory"

        metrics = run_simulation(config, queries, seed=seed + offset)
        runs.append(metrics.to_report_dict())

    numeric_keys = [
        "availability",
        "error_rate",
        "latency_p50_ms",
        "latency_p95_ms",
        "latency_p99_ms",
        "fallback_success_rate",
        "cache_hit_rate",
        "circuit_open_count",
        "recovery_time_ms",
        "estimated_cost",
        "estimated_cost_saved",
    ]

    averages: dict[str, object] = {
        key: round(
            average(
                [
                    float(run[key])
                    for run in runs
                    if run[key] is not None
                ]
            ),
            4,
        )
        for key in numeric_keys
    }
    averages["total_requests"] = requests * len(base_config.scenarios)
    averages["repeats"] = repeats
    averages["requests_per_scenario"] = requests
    averages["seed_start"] = seed
    averages["mode"] = mode
    averages["runs"] = runs
    return averages


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", default="configs/default.yaml")
    parser.add_argument("--out", default="reports/benchmark_cache_modes.json")
    parser.add_argument("--requests", type=int, default=1000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20260701)
    args = parser.parse_args()

    results = {
        mode: benchmark_mode(args.config, mode, args.requests, args.repeats, args.seed)
        for mode in ["no-cache", "memory", "redis"]
    }

    output_path = Path(args.out)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2))
    print(f"wrote {args.out}")


if __name__ == "__main__":
    main()
