"""Run an independent example through Lean and export its complete artifact."""

import argparse
from pathlib import Path

from equireduce import LeanConfig, export_artifact, reduce_in_coordinates, reduce_system

from . import bjt14, bjt43, flow_balance, kinematic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "example", choices=("bjt14", "bjt43", "bjt143", "flow_balance", "kinematic")
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    proof_options = {
        "proof": "require",
        "lean": LeanConfig(str(root / "lean"), timeout_seconds=180),
    }
    if args.example in ("bjt43", "bjt143"):
        system, transform, candidates = (
            bjt43.make_full_system()
            if args.example == "bjt143"
            else bjt43.make_system()
        )
        result = reduce_in_coordinates(
            system, transform, candidates=candidates, **proof_options
        )
    else:
        module = {"bjt14": bjt14, "flow_balance": flow_balance, "kinematic": kinematic}[
            args.example
        ]
        system, candidates = module.make_system()
        result = reduce_system(system, candidates=candidates, **proof_options)
    output = args.output or root / "examples/output" / args.example
    export_artifact(result, output)
    print(f"{len(system.unknowns)} -> {len(result.remaining_unknowns)} unknowns")
    print(f"Lean: {result.formal_check.status.value}; coverage: {result.coverage}")
    print(f"Artifact: {output}")


if __name__ == "__main__":
    main()
