# Python API: implementation and future extensions

Algebraic `System`, `reduce_system`, certificate verification, Lean modes,
and artifact operations are implemented in `0.1.0.dev0`.
Exact signatures appear in the [generated reference](reference.md).
Coordinates and search are described [separately](coordinates.md), and the
experimental DAE API in the [DAE contract](dae.md).

## Creating an algebraic system

```python
import sympy as sp
from equireduce import System

x, y, a = sp.symbols("x y a", real=True)

system = System.algebraic(
    residuals=(a*y - x, y + x - 1),
    unknowns=(x, y),
    parameters=(a,),
    conditions=(sp.Ne(a, 0),),
)
```

`residuals` are `Expr` objects, each set equal to zero. The initial API does
not accept strings or `Eq`: this avoids ambiguity between a residual, an
equality, and an already evaluated Boolean. A `Matrix` can be normalized
into an ordered tuple of scalar residuals.

`unknowns` contains distinct real `Symbol` objects, preserving order.
`parameters` explicitly declares other free symbols and is disjoint from the
unknowns. Examples should use `real=True`; unknown or incompatible assumptions
are not silently reinterpreted. `conditions` contains SymPy predicates.
Empty tuples are allowed. Sign assumptions on symbols and undefined functions
are included in the domain. Discrete assumptions such as `integer=True` are
unsupported. For explicit conversion of decimal coefficients, the factory has
`float_policy="exact_decimal"`; numbers in the resulting system are exact.

Hidden free symbols, `Derivative` in the algebraic domain, invalid numbers,
and repeated unknowns cause validation errors. An empty system is valid and
means no constraints within the specified domain.

## Main operation

```python
def reduce_system(
    system: System,
    *,
    candidates=None,
    options=None,
    proof="none",
    lean=None,
) -> ReductionResult:
    ...
```

- `candidates`: unknowns explicitly eligible for elimination; `None` permits
  considering all of them. Order is a search preference, not permission for
  an invalid step.
- `options`: immutable `ReductionOptions` with budgets and a selection criterion.
- `proof`: `"none"`, `"generate"`, or `"require"`.
- `lean`: `LeanConfig` with the pinned Lake project's working directory,
  a command tuple, and a timeout.

`coordinate_search=True` searches a finite family of charts.
`max_candidates` bounds evaluated charts; `coefficient_bound` bounds integer
coordinate shear coefficients. `allow_blocks=False` restricts elimination to
scalar steps. The decimal policy applies when creating `System`, not after
input precision has already been lost.

```python
from equireduce import LeanConfig, ReductionOptions, reduce_system

options = ReductionOptions(
    max_candidates=32,
    coordinate_search=False,
    float_policy="reject",
)
lean = LeanConfig(
    project_dir="./lean",
    command=("lake", "env", "lean"),
    timeout_seconds=120,
)

result = reduce_system(
    system,
    candidates=(y,),
    options=options,
    proof="require",
    lean=lean,
)
```

`project_dir` is explicit rather than inferred from the current process.
The command is not passed to a shell. Parameters must have checkable bounds,
such as positive integer budgets and a positive timeout.

## Result

| `ReductionResult` field | Meaning |
|---|---|
| `source` | Immutable source `System` |
| `reduced_system` | Reduced residuals and their domain as SymPy objects |
| `remaining_unknowns` | Ordered final coordinates |
| `reconstruction` | SymPy mapping for all eliminated variables |
| `coordinate_map` | Forward and inverse charts when coordinates change |
| `conditions` | All result conditions with provenance |
| `additional_conditions` | New restrictions relative to the input domain |
| `coverage` | `complete` relative to the input domain, or `conditional` |
| `assumption_consistency` | `consistent`, `inconsistent`, or `unknown` |
| `certificate` | Versioned trace of checkable steps |
| `symbolic_check` | Separate SymPy verification status |
| `formal_check` | Lean status, theorem, source, versions, and log |
| `metrics` | Complexity comparison before and after reduction |
| `search` | Budget, candidate count, family completeness, and termination reason |

For plain reduction, `coordinate_map` and `metrics` are `None`, while `search`
records the deterministic algorithm's termination reason. The formal result
also has `origin`, `command`, `seconds`, `checked_at_utc`, and a source hash.
After artifact loading, `origin="recorded"` identifies a historical result,
not fresh compilation.

`reduced_system.residuals` and `reconstruction` must remain SymPy objects.
Text representations are intended for documentation and export, not mandatory
reparsing within the Python API.

`coverage="complete"` is valid only if the certificate does not restrict the
input solution set, or if the new conditions are proved to follow from it.
It makes no claim about search completeness or existence of solutions.

## Proof modes

| `proof` | Expected behavior |
|---|---|
| `none` | Symbolic verification; Lean is not run, status `not_requested` |
| `generate` | Source is generated; status `generated` if export is supported |
| `require` | A certified result is returned only after actual Lean verification |

With `require`, missing Lean, a timeout, unsupported export, or a rejected
proof raises `ProofVerificationError` with diagnostics and access to the
unconfirmed candidate. There is no silent fallback to `none`.
Generated text never has `verified` status.

In other modes, unsupported export is reported in `formal_check`; a valid
symbolic result can be inspected without claiming formal verification.
An unverified symbolic candidate is not presented as a confirmed reduction:
the source system is returned with diagnostics, or an explicit error is raised.

## Separate operations

Public functions:

```python
def verify_certificate(system, certificate): ...
def generate_lean(system, certificate, *, config): ...
def verify_with_lean(system, certificate, *, config): ...
def export_artifact(result, path): ...
def load_artifact(path): ...
```

File export is an explicit user operation. Artifact loading checks the schema
and integrity; it does not run Lean or automatically repeat the formal proof.

## Exceptions

The base exception is `EquiReduceError`, with subclasses `InvalidSystemError`,
`UnsupportedDomainError`, `UnsupportedExpressionError`, `CertificateError`,
`ProofVerificationError`, and `ArtifactError`.
Messages identify the equation index, variable, or expression node path where
the problem occurred. Failure to find a reduction is not itself an exception.
A contradictory system is also a mathematical result if the contradiction
has actually been justified.

## Experimental DAE API

`DAESystem.semi_explicit(...)` and `reduce_dae(...)` accept time functions,
a square affine algebraic block, and an open interval. They return
`DAEReductionResult` with reconstruction, first derivatives, interval-wide
conditions, and initial data checks. `verify_dae_certificate` checks a separate
DAE certificate. Algebraic `System.algebraic` continues to reject derivatives.
