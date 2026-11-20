# Implicit DAEs: stages DN-DAE-01–12

This API accepts general first-order residuals and preserves implicit dynamics.
It is separate from `DAESystem.semi_explicit`, with its own complete Lean
theorem connecting source MNA rows to the final DAE.

## Contract

```python
import sympy as sp
from equireduce import ImplicitDAESystem, reduce_implicit_dae

t, C = sp.symbols("t C", real=True)
x, y = (sp.Function(name, real=True)(t) for name in ("x", "y"))
source = ImplicitDAESystem.create(
    time=t, unknowns=(x,y), differential=(x,), algebraic=(y,),
    residuals=(C*sp.diff(x,t)+sp.diff(y,t)+y, y-x**2),
    parameters=(C,), interval=(-1,1),
    residual_names=("dynamic", "constraint"),
)
result = reduce_implicit_dae(source)
assert result.reconstruction[y] == x**2
assert result.reconstruction_derivatives[sp.diff(y,t)] == 2*x*sp.diff(x,t)
assert sp.expand(result.reduced_system.residuals[0] -
    ((C+2*x)*sp.diff(x,t)+x**2)) == 0
assert result.coverage == "complete"
assert not result.conditions
```

`unknowns` preserves source variable order. `differential` and `algebraic`
must be disjoint and together partition `unknowns`. This is an elimination
request, not an automatic proof of state independence or DAE index.
Either partition part may be empty.

States and `inputs` are explicitly real functions of the declared time.
Parameters are separate real constant symbols. Declare an input `u(t)` in
`inputs`; neither it nor its first derivative becomes a constant parameter.
The initial contract supports differentiable trajectories on an open interval
with finite exact endpoints. `interval_condition` returns a nonemptiness
condition when the endpoints are symbolic.

Strings are not parsed as expressions. `Float`, higher derivatives,
derivatives with respect to another variable, and nonsmooth operators produce
explicit errors. `Piecewise` requires an explicit smooth branch choice.
State signs and partial-operation domains are preserved before substitutions
and possible cancellations.

## Structure and rank

`analyze_implicit_dae(source)` normalizes first derivatives of composite
expressions in the supported smooth class, constructs
$E=\partial F/\partial\dot X$, and checks the identity $F=E\dot X+h$ itself.
Coefficients in $E$ and $h$ cannot depend on unknown-state rates.
For example, $\dot x^2$ is not affine merely because its Jacobian can be computed.

The result includes the source system, normalized residuals, derivative expansion
trace, immutable mass matrix, offset, and rank report.
`verify_implicit_structure` recomputes and checks these fields.

Rank is determined by exact minors with a deterministic `max_minors` budget
(default 64):

| Status | Meaning |
|---|---|
| `exact` | Lower and upper bounds agree under the input domain |
| `conditional` | Rank is proved under an explicitly returned additional minor condition |
| `unknown` | Only bounds remain; undefined functions or the budget prevented an exact rank proof |

Graph matching supplies only a structural upper bound. The report also contains
a witness determinant, minor indices, evaluation count, and a budget-exhaustion
flag. No numerical rank or random parameter testing is used. Diagnostic rank
conditions are not automatically added to the reduced DAE's domain.

## Algebraic elimination

For the initial class, the algebraic block must be available in derivative-free
rows after normalization. The pipeline uses EquiReduce's shared affine reducer;
Dnipro has no separate copy of the mathematical algorithm. The entire requested
algebraic set must be eliminated. This first class does not derive new algebraic
constraints by differentiation or combinations of dynamic rows.

Reconstruction $y=\varphi(t,x,p,u)$ uses rational operations, `exp`, and declared
smooth laws and is independent of rates. It computes
$\dot y=\varphi_t+\varphi_x\dot x+\varphi_u\dot u$, then transforms all
source rows and domains. Additional algebraic constraints are retained.
Only exactly zero row images are removed. `residual_source_indices` links each
final row to its source.

The mass matrix is not inverted. For example,
$C\dot v+(v-U_0)/R=0$ introduces no new condition $C\ne0$.
When $C=0$, the algebraic case remains; it is not declared an ODE.
`form="implicit"` and `index_status="not_classified"` describe the result.

Unsupported functions, an uneliminated algebraic block, and nonlinear dependence
on state rates are currently rejected. Prescribed inputs and their first
derivatives are retained in both dynamic rows and reconstruction.
Supported BJT charge profiles are described below.

## Certificate and Lean

`verify_implicit_certificate(source, result.certificate)` checks:

1. The source snapshot and derivative normalization.
2. Selected source algebraic rows and their domain.
3. The affine elimination trace without repeating search.
4. Reconstruction, its derivatives, all residuals, and their source indices.
5. Preservation of input and added conditions.

`formal_check` defaults to `not_requested`. `proof="generate"` generates the
theorem; `proof="require"` runs actual Lean using `LeanConfig(project_dir)`.
An unsupported expression language yields `unsupported`; an incomplete
required proof raises `ProofVerificationError`.

`reduction_equivalence` proves both directions between original rows with
their domains and the reduced system with the reconstruction graph for
differentiable trajectories on an open interval. Final domain conditions are
assumed throughout the interval. Lean derivatives are actual derivatives:
`HasDerivAt`, `deriv`, the chain rule, and equality near a point.
Source rational rows are printed with their structure preserved, so a pole
removed by cancellation is not lost from the source theorem.
The final composed theorem's axioms are audited.

This backend currently rejects a nonzero static pivot row that became static
only after derivative expansion. `C1` regularity, solution existence/uniqueness,
and general index reduction are not claimed.

## Initial data

```python
checked = reduce_implicit_dae(
    source, initial_time=0, initial_values={x: 0}, parameter_values={C: 0},
)
assert checked.initial_check.status == "verified"
```

Every retained state is required; eliminated values can be reconstructed.
Supplied values and rates are never corrected. `initial_rates` uses
`Derivative(state, time)` keys. Cyclic parameter assignments, inexact numbers,
and points on the interval boundary are rejected. Parameters are also
substituted exactly into the initial time.

`initial_check` returns `verified` or `conditional`, rejecting proved
inconsistency with `InvalidSystemError`. `obligations` contains symbolic
conditions; `rate_equations` / `rate_conditions` contain obligations for
existence of missing rates. `rate_witness` contains a proved exact witness
when one was constructed without new assumptions. No new $C\ne0$ or $L\ne0$
is assumed merely to compute a rate.

The check scope is `pointwise_residuals_and_reconstruction`, with
`trajectory_existence="not_asserted"`. It does not guarantee trajectory
existence or fully search for hidden higher-index constraints.

## Prescribed time-dependent inputs

Declaring `inputs=(u, ...)` means each input function is externally prescribed
and differentiable throughout the system's open interval.
`source.input_regularity` returns function/assumption pairs. Inputs become
neither constant parameters nor unknown trajectories. Both correspondence
directions use the same prescribed input.

```python
u = sp.Function("input", real=True)(t)
driven = ImplicitDAESystem.create(
    time=t, unknowns=(x,y), differential=(x,), algebraic=(y,),
    residuals=(sp.diff(x,t)+sp.diff(y,t)+y, y-x*u**2),
    inputs=(u,), interval=(-1,1),
)
driven_result = reduce_implicit_dae(
    driven, initial_time=0, initial_values={x:2},
    initial_input_values={u:3},
    initial_input_rates={sp.diff(u,t):5},
)
assert driven_result.required_input_rates == (sp.diff(u,t),)
assert driven_result.initial_check.status == "verified"
assert dict(driven_result.initial_check.values)[y] == 18
```

For this example,

$$\dot y=u^2\dot x+2xu\dot u,$$
$$ (1+u^2)\dot x+2xu\dot u+xu^2=0.$$

`required_input_rates` contains required first derivatives in declared input
order, including source normalized rows and conditions. The chain rule
accounts for every input and denominator domain.

In Lean, inputs are separate `ℝ → ℝ` functions; `hInputRegularity` assumes
`DifferentiableAt` for each at every interval point. The chain rule uses their
actual `deriv` and `HasDerivAt`. The assumption also appears in the complete
time-chart theorem. A kernel test rejects zeroing $\dot u$.

`initial_input_values` keys are declared functions; `initial_input_rates`
keys are their first derivatives. Supplied samples are unchanged.
Missing values for every declared input and required derivative receive fresh
real symbols in `initial_check.input_values`, `input_rates`, and
`input_unknowns`. Status is then `conditional`. These symbols are separate
from existential missing state rates: the check does not choose an external
signal to satisfy the equations. Input sign conditions, poles, and exactness
are checked together with the other data.

The same arguments are available in `search_implicit_partitions`,
`reduce_implicit_in_coordinates`, and the Dnipro adapter methods.
Reconstruction involving $\dot u$ is currently forbidden because its
differentiation could introduce $\ddot u$.

The formal statement is conditional on the specified differentiability.
It does not prove smoothness of a particular nonrational signal formula or
correctness across a jump. `Piecewise`, PWL/PULSE at switching points, and
nonsmooth operators remain outside this input contract.

## Automatic partitioning

```python
from equireduce import search_implicit_partitions

best = search_implicit_partitions(
    source, preferred_differential=(x,), max_candidates=32,
)
assert best.search.candidates_evaluated <= 32
```

Search considers a deterministic finite family of partitions based on state
occurrence in derivative-free rows. The first candidate eliminates nothing;
the largest blocks follow. Every successful candidate has a verified
certificate. The score minimizes state count, additional conditions, and
operations. `preferred_differential` retains specified states in every candidate.
`result.source` contains the selected partition; `result.search.source`
contains the initial source. `complete` means exhaustion of the declared
family, not a global minimum or independence of physical states.

## Time-dependent coordinates

```python
from equireduce import TimeAffineTransform, reduce_implicit_in_coordinates

u, v = (sp.Function(n, real=True)(t) for n in ("u", "v"))
chart = TimeAffineTransform.create(
    source, variables=(u, v), matrix=((1, 0), (t, 1)), offset=(t**2, 0),
)
mapped = reduce_implicit_in_coordinates(
    source, chart, differential=(u,), algebraic=(v,),
)
```

Invertible square charts $X=M(t,p)U+c(t,p)$ with rational coefficients are
supported. Forward and inverse maps, both rate maps, and domains are retained;
$M\dot U+\dot M U+\dot c$ is included. New coordinates are fresh unrestricted
real time functions. The determinant condition holds throughout the interval.

`verify_time_transform` checks the chart itself;
`verify_implicit_coordinate_certificate` checks composition with elimination.
The formal theorem existentially constructs new trajectories through the
inverse chart, proves their differentiability, and both directions from source
rows. Its domain hypothesis consists of final conditions transported by the
inverse chart. Initial values may be supplied in retained new coordinates or
for all original states; contradictory simultaneous values are rejected.
`certificate.inner` retains the augmented system with coordinate rows;
`residual_source_indices` indexes its rows, not only the original ones.

## Smooth charge laws and branches

```python
from equireduce import SmoothFunction

Qbe = SmoothFunction("Qbe", 2)
# Qbe.function(vbe, vbc), Qbe.partials[0](vbe, vbc), Qbe.partials[1](vbe, vbc)
```

A one- or two-variable law declaration defines a function and names for its
partial derivatives. SymPy retains the derivatives as declared functions
`Qbe__d0`, `Qbe__d1`. In Lean, `hSmooth` specifies an actual `HasDerivAt` or
joint `HasFDerivAt` with the corresponding gradient at every point.
The two-variable case proves composition with a pair of trajectories using
`HasDerivAt.prodMk` and `comp_hasDerivAt`. Derivative assumptions are part
of the contract, not an axiom asserting equivalence of the final and source
systems. This is a structural result for laws satisfying the declared global
differentiability.

Pass declarations as `smooth_functions=(Qbe, ...)` when creating
`ImplicitDAESystem`. Nested compositions, products, and quotients are supported.
Reconstruction and charge normalization preserve every partial derivative,
including mixed dependence of BE charge on BC voltage. Concrete `exp` uses
proved Mathlib theorems without `hSmooth` for that function.

`branch_choices=((piecewise_expression, branch_index), ...)` selects exactly
one branch of every `Piecewise` node. Branch order is respected; complements
of preceding conditions are strengthened to strict inequalities.
The selected branch's region enters the source system throughout the interval.
Raw `Piecewise` and charge `Derivative` remain in the source and Lean statement.
The selected smooth formula's derivative transfers to the source function by
equality near a point, not substitution at only one point. Boundaries, jumps,
and transitions between branches are not covered. Here, `coverage="complete"`
means completeness within the declared region.

Concrete Dnipro NPN and PNP tests use fixed `VT`, `MJE=MJC=0`, zero additional
options, and nonzero `CJE/CJC`, `TF/TR`, and Early effect. Both forward-storage
branches have their own domains and actual Lean proofs of the source charge
MNA. Current and charge formulas are unchanged. The profile contains nonlinear
exponential charge and mixed derivatives through base charge. Separately,
$Q_c+Q_b+Q_e=0$ and the balance of their time derivatives are proved.

This does not support every BJT parameter. Dynamic noninteger powers in graded
junctions (`MJE/MJC ≠ 0`), roots, undeclared special functions, branch switching,
and general inversion of $Q(V)$ currently receive explicit diagnostics.
Introducing charge does not prove its independence or authorize inversion
of a nonlinear law.

## Portable result

`export_artifact(result, path)` and `load_artifact(path)` support manual
reduction, time charts, inputs, smooth laws, branches, initial data, and search
reports. The schema namespace is `equireduce.implicit/v1`, with machine-readable
description `artifact-implicit-v1.schema.json`. The old algebraic/semi-explicit
format remains separate. Loading rebuilds mathematical fields from a checked
certificate without repeating elimination; the search report is separately
checked by replaying only its declared candidates.

`formal_check.origin="recorded"` identifies a historical run report.
For fresh compilation, call `verify_with_lean` or Dnipro `verify-dae`.
Stored code is not executed on loading; it must also match the code freshly
generated from the certificate exactly.
