"""Measure actual Lean time for a small declared coordinate search family."""

import argparse
import json
from pathlib import Path

import sympy as sp

from equireduce import (
    LeanConfig,
    ReductionOptions,
    System,
    benchmark_coordinates,
    search_coordinates,
)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--max-candidates", type=int, default=3)
    parser.add_argument(
        "--output", type=Path, default=Path("examples/output/coordinate-benchmark.json")
    )
    args = parser.parse_args()
    x, y, a, b = sp.symbols("x y a b", real=True)
    source = System.algebraic((x + y - a, (x - y) ** 2 - b), (x, y), parameters=(a, b))
    result = search_coordinates(source, options=ReductionOptions(max_candidates=11))
    report = benchmark_coordinates(
        source,
        result.search,
        max_candidates=args.max_candidates,
        lean=LeanConfig(str(Path(__file__).resolve().parents[1] / "lean")),
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.to_record(), indent=2) + "\n")
    print(
        f"Measured {len(report.entries)} candidates; "
        f"Spearman: {report.spearman_correlation}"
    )
    print(args.output)


if __name__ == "__main__":
    main()
