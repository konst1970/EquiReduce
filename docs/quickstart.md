# Getting started

This guide covers the implemented algebraic version `0.1.0.dev0`.
Coordinate search and experimental DAEs have separate sections.
Run the commands from the `EquiReduce` root.

## Installation

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,docs]'
```

For core use only, `pip install -e .` is sufficient.
Python 3.11+ and SymPy 1.14 are required; Lean is not required for import.

## Reduction in SymPy

```python
import sympy as sp
from equireduce import System, reduce_system, verify_certificate

x, y, a = sp.symbols("x y a", real=True)
system = System.algebraic(
    (a*y - x, y + x - 1), (x, y),
    parameters=(a,), conditions=(sp.Ne(a, 0),),
)
result = reduce_system(system, candidates=(y,))
assert result.reconstruction[y] == x/a
assert result.remaining_unknowns == (x,)
assert result.coverage == "complete"
assert verify_certificate(system, result.certificate).status.value == "verified"
print(result.reduced_system.residuals)
```

The remaining equation is equivalent to `x/a + x - 1 = 0`.
Without the source condition `a != 0`, the result has `coverage="conditional"`,
and the condition appears in `additional_conditions`.
Sign assumptions are supported. Derivatives, discrete domains, and strings
in place of SymPy expressions are explicitly rejected.

## Lean verification

Install Elan/Lean separately. Prepare the pinned Lake project:

```bash
cd lean
MATHLIB_NO_CACHE_ON_UPDATE=1 lake update
lake exe cache get Mathlib.Basic.Real.Basic Mathlib.Tactic.FieldSimp Mathlib.Tactic.LinearCombination Mathlib.Tactic.Linarith Mathlib.Tactic.NormNum Mathlib.Tactic.Ring Mathlib.Analysis.Calculus.Deriv.Pow Mathlib.Analysis.Calculus.Deriv.Inv Mathlib.Analysis.Calculus.Deriv.Add Mathlib.Analysis.Calculus.Deriv.Prod Mathlib.Analysis.SpecialFunctions.ExpDeriv Mathlib.Tactic.Convert
cd ..
```

After preparing the dependencies:

```python
from equireduce import LeanConfig, reduce_system

verified = reduce_system(
    system, candidates=(y,), proof="require",
    lean=LeanConfig(project_dir="lean"),
)
assert verified.formal_check.status.value == "verified"
print(verified.formal_check.axioms)
```

`proof="generate"` only creates source code. `proof="require"` returns a result
only after compilation and axiom auditing.
The current formal subset includes rational arithmetic, integer powers,
condition predicates, and opaque functions. For example, explicit `sin` in a
residual yields `unsupported` rather than an unsupported claim of proof.

## Portable bundle

```python
from equireduce import export_artifact, load_artifact

export_artifact(verified, "examples/output/my-proof")
restored = load_artifact("examples/output/my-proof")
assert restored.reconstruction == verified.reconstruction
assert restored.formal_check.origin == "recorded"
```

For fresh compilation, call `verify_with_lean` with the loaded `source` and
`certificate`. Loading JSON does not run Lean.
To write only JSON, pass a path with the `.json` suffix.

## Acceptance examples

```bash
.venv/bin/python examples/flow_balance.py
.venv/bin/python examples/kinematic.py
.venv/bin/python -m examples.run_formal flow_balance
.venv/bin/python -m examples.run_formal kinematic
.venv/bin/python -m examples.run_formal bjt14
.venv/bin/python -m examples.run_formal bjt43
.venv/bin/python -m examples.run_formal bjt143
.venv/bin/python -m examples.dae_first_order
.venv/bin/python -m examples.coordinate_benchmark
```

The formal examples create verified bundles in `examples/output/`.
`bjt14` accepts all 14 source equations and reconstructs 10 eliminated
variables; the old Dnipro Lean file is not used as its proof.
`bjt143` additionally specifies dependence on voltage differences and proves
the full transition from 14 source equations to three coordinates.

## Checks

```bash
.venv/bin/python -m pytest -m 'not lean'
EQUIREDUCE_REQUIRE_LEAN=1 .venv/bin/python -m pytest -m lean
.venv/bin/python -m ruff check src tests examples
.venv/bin/python -m mypy src/equireduce
.venv/bin/python -m sphinx -n -W --keep-going -b html docs docs/_build/html
```

Tests requiring Lean are skipped locally if its environment is not prepared.
With `EQUIREDUCE_REQUIRE_LEAN=1`, this is an error. Tests that mock the process
are not treated as evidence of mathematical correctness.
