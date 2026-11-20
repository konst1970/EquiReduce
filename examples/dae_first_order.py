"""Run the first semi-explicit DAE through actual Lean and export its proof."""

from pathlib import Path

import sympy as sp

from equireduce import DAESystem, LeanConfig, export_artifact, reduce_dae


def main():
    t = sp.Symbol("t", real=True)
    x, y = (sp.Function(name, real=True)(t) for name in ("x", "y"))
    source = DAESystem.semi_explicit(
        time=t,
        differential=(x,),
        algebraic=(y,),
        rhs=(-y,),
        constraints=(y - x**2,),
        interval=(-1, 1),
    )
    root = Path(__file__).resolve().parents[1]
    result = reduce_dae(
        source,
        initial_time=0,
        initial_values={x: 2, y: 4},
        proof="require",
        lean=LeanConfig(str(root / "lean")),
    )
    destination = export_artifact(result, root / "examples/output/dae-first-order")
    print(result.reduced_residuals)
    print(dict(result.reconstruction_derivatives))
    print(
        f"Lean: {result.formal_check.status.value}; "
        f"initial data: {result.initial_check.status}"
    )
    print(destination)


if __name__ == "__main__":
    main()
