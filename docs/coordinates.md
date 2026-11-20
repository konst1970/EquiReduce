# Coordinates, search, and measurements

## Explicit affine chart

`AffineTransform.create` defines $X=MU+c$, with coefficients depending only
on declared parameters. New coordinates are fresh unrestricted real symbols.
The matrix must be square and invertible; required nonzero determinant and
denominator conditions are returned explicitly.

```python
import sympy as sp
from equireduce import System, AffineTransform, reduce_in_coordinates

x, y, u, v = sp.symbols("x y u v", real=True)
system = System.algebraic((x+y-2, (x-y)**2-1), (x,y))
chart = AffineTransform.create(system, variables=(u,v), matrix=((1,1),(1,-1)))
result = reduce_in_coordinates(system, chart, candidates=(u,))
assert result.remaining_unknowns == (v,)
assert result.reconstruction == {x: 1+v, y: 1-v}
```

`result.source` retains the source system. The composed certificate contains
the chart, inverse chart, and elimination trace in the new coordinates.
Independent verification rechecks every part. Lean proves full equivalence
with existence of the new coordinates and reconstruction of the source
variables. A certificate for only the inner system is insufficient.

## Finite search

```python
from equireduce import ReductionOptions, search_coordinates

best = search_coordinates(system, options=ReductionOptions(
    max_candidates=11, coefficient_bound=2,
))
assert best.search.candidates_evaluated <= 11
```

The `integer-affine-and-shared-reference/v1` family contains the identity
chart, shared-reference coordinates for dimensions of at least three, pairwise
permutations, integer shears, and sum/difference charts. Its order is fixed.
For $n$ coordinates and bound $b$, the family size is

$$1+n(n-1)(2b+1)+\begin{cases}n,&n\ge3,\\0,&n<3.\end{cases}$$

The budget bounds the number of charts, not the duration of a single symbolic
step. The report contains the budget, available/evaluated chart counts, the
selected index, and `complete`. Completeness applies only to the declared
family; it does not prove a global minimum over all possible coordinates.
`reduce_system(..., options=ReductionOptions(coordinate_search=True))`
uses the same search. Specify explicit `candidates` through
`reduce_in_coordinates`, where the new variable names are known.

The lexicographic score accounts for the final unknown count, Jacobian
operations, residual operations, DAG size, additional conditions, and matrix
simplicity. The Jacobian is used as a metric; no numerical solver runs.
Search reports are diagnostic data rather than the mathematical part of a
certificate or an independent optimality proof.

## Actual Lean benchmark

`benchmark_coordinates(system, best.search, max_candidates=3, lean=...)`
rebuilds selected candidates and measures source generation and actual Lean
verification. It records time, status, versions, hashes, and Spearman
correlation between the score and the duration of successful checks.
Fewer than two measurements or a constant score yield `None`, not an invented
value.

```bash
.venv/bin/python -m examples.coordinate_benchmark
```

Timing depends on the machine, cache, and compiler startup. One local run of
three candidates gave correlation `-1.0`; this does not validate the score as
a timing predictor. The selection algorithm does not present it as measured
time or a universally validated model.

## BJT regressions

`examples.bjt43` defines the chart
$v_{bi}=u_{be}+e$, $v_{ci}=u_{be}-u_{bci}+e$, $v_{ei}=e$,
$v_x=u_{be}-u_{bcx}+e$. When device functions depend on voltage differences,
eliminating $e$ leaves three unknowns.

The `bjt43` and `bjt143` commands in `examples.run_formal` compile 4 → 3 and
the full 14 → 3 transition, respectively. These are structural fixtures with
arbitrary real functions, not proofs of the physical laws of a concrete BJT
model. The base `bjt14` fixture retains weaker assumptions and checks 14 → 4.
