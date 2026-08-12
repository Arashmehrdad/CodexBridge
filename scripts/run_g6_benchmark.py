"""Run or preflight the isolated real-provider G6 canonical benchmark."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from soma.agent_worker_benchmark_runtime import (
    G6_REAL_MISSION_ID,
    ensure_model_turn_ceiling,
    prepare_g6_runtime,
    provider_send_boundaries_crossed,
    run_real_g6_trial,
)
from soma.config import load_config


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode", choices=("setup", "preflight", "trial", "status"), required=True
    )
    parser.add_argument("--phase", choices=("screening", "confirmation"), default="screening")
    parser.add_argument("--condition", type=int, choices=(1, 2, 4, 8), default=1)
    parser.add_argument("--repetition", type=int, default=1)
    parser.add_argument("--model-turn-ceiling", type=int, default=32)
    return parser


def main() -> int:
    args = _parser().parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    config_path = repo_root / "config.yaml"
    runtime = prepare_g6_runtime(
        repo_root=repo_root,
        base_config=load_config(config_path),
        config_path=config_path,
        repo_name="soma",
    )
    quota = ensure_model_turn_ceiling(runtime, args.model_turn_ceiling)

    if args.mode == "preflight":
        output = {
            "mode": "preflight",
            "mission_id": G6_REAL_MISSION_ID,
            "runs_dir": str(runtime.runs_dir),
            "quota": quota,
            "provider": dict(runtime.reasoning_backend.preflight()),
        }
    elif args.mode == "trial":
        result = run_real_g6_trial(
            runtime,
            phase=args.phase,
            concurrency=args.condition,
            repetition=args.repetition,
            model_turn_ceiling=args.model_turn_ceiling,
        )
        output = {
            "mode": "trial",
            "result": result.model_dump(mode="json"),
            "provider_send_boundaries_crossed": provider_send_boundaries_crossed(runtime),
        }
    else:
        output = {
            "mode": args.mode,
            "mission_id": G6_REAL_MISSION_ID,
            "runs_dir": str(runtime.runs_dir),
            "quota": quota,
        }

    print(json.dumps(output, sort_keys=True, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
