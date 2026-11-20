# Testing and quality criteria

This section defines the general validation strategy. Implemented algebraic
and Lean tests and actual results are described in the [TDD report](progress.md).
Positive and negative DAE tests include actual proofs for polynomial,
time-dependent rational and parametric reconstruction, and a coupled block.
General extensions outside this class remain requirements.

## Verification levels

| Level | What it checks | What it does not establish |
|---|---|---|
| Structural | Types, domains, reconstruction order, and completeness | Equation identities |
| Symbolic | Exact transformations and the certificate in SymPy | An independent Lean proof |
| Formal | A specific theorem through actual Lean | Physical correctness of the input model |
| Differential | Comparison of independent implementations | A proof for every parameter value |

## Unit tests

- Input: empty, rectangular, and redundant systems, repeated symbols, hidden
  parameters, inexact numbers, and derivatives in the wrong domain.
- Affinity: constant, scalar, and block dependencies, nonlinear obstacles,
  undefined functions, and `unknown` instead of a forced decision.
- Conditions: zero denominators, singular blocks, contradictory assumptions,
  inherited constraints, and new restrictions.
- Reconstruction: order, completeness, absence of cycles, and composition
  of multiple eliminations and coordinate charts.
- Search: determinism, budget compliance, and correctly reported incompleteness.
- Serialization: exact round trips and rejection of unknown schemas, corrupted
  IDs, unsupported nodes, and excessive sizes.
- Runner: missing tools, nonzero exit codes, timeouts, and input errors.

Mocking the Lean process is allowed only for the last group. Such tests do
not count as successful formal proofs.

## Integration tests with actual Lean

Required positive examples include scalar elimination with a nonzero symbolic
coefficient, an invertible block, a conditional coordinate transformation,
step composition, and an opaque nonlinear function.

Every claimed export class needs an actual example, including `Piecewise`
boundaries, roots, and logarithms if they are declared supported.
Formatting generated source is not a sufficient test.

Negative checks change one meaningful element of a valid example:

- A sign or coefficient in a reduced equation.
- A reconstruction formula for an eliminated variable.
- A necessary nonsingularity condition.
- An opaque function argument.
- Branch coverage.
- An axiom or a proof replaced with `sorry`.

The test must establish rejection of the mathematical error rather than a
missing import or unavailable compiler. A positive control example checks
that the environment is prepared.

## Properties and regressions

Generate small exact affine blocks with rational coefficients embedded in a
nonlinear core. Check bidirectional certificates, coordinate permutations,
domain preservation, and determinism. Randomized examples have bounded sizes
and reproducible seeds.

The regression set includes Dnipro 14 → 4, examples outside electronics,
degenerate cases, and every discovered exporter counterexample. A change in
hash or printed form is not itself a mathematical regression; compare the
contract and content.

## DAE acceptance suite

Implemented coverage includes affine algebraic elimination, time-dependent
charts, prescribed inputs, consistent and inconsistent initial data, pole
preservation, smooth charge laws, and selected open `Piecewise` regions.
High index, nonsmooth points, and higher derivatives have negative contract
checks rather than supported solving status.

The smooth suite includes both charge partial derivatives, actual `exp`,
reconstruction involving `exp`, composition with a time chart, and rejection
of a substituted gradient by actual Lean. Concrete NPN/PNP models with fixed
VT, MJE=MJC=0, TF/TR, and Early effect are checked for both claimed branches;
collector, base, and emitter balance is proved separately.

Artifacts are checked after changes to structure, coverage, initial data, and
source labels with recomputed SHA-256 hashes. CLI coverage includes JSON,
LaTeX, Lean, text, reloading, and input binding. Supported-path tests block
`nsolve`, `Expr.equals`, and numerical `Matrix.rank`. Numerical integration
and SPICE are not part of these criteria.

Formal support for a DAE class requires interval Lean theorems. Inspecting
generated source text does not replace compilation of positive and meaningful
negative examples.

## CI

Planned independent jobs:

1. Ruff and type annotation checks.
2. Ordinary Python tests on every claimed Python version.
3. Lean integration tests on the pinned toolchain.
4. Sphinx HTML build with warnings treated as errors.
5. Wheel/sdist builds and wheel installation in a clean environment.

Markers `unit`, `integration`, `lean`, and `slow` are registered in
`pyproject.toml`. Formal backend CI must not silently skip Lean tests.
In a local environment without Lean, skipping is allowed and visible.

Python versions in the matrix are determined by actual runs, starting with
the minimum 3.11; new versions must not be called tested solely because of
`requires-python`.

## First-release readiness criterion

- Independent installation without Dnipro and import without Lean.
- Confirmed exact reconstruction and domain preservation.
- Actual positive and negative Lean tests without `sorryAx`.
- Migration validation for 14 → 4 and at least two examples outside electronics.
- Reproducible artifacts and verified wheel installation.
- Documentation matches implementation; available API examples execute.
- No hidden fallback from requested formal proof to CAS.

## Performance

Measure preparation, search, SymPy verification, Lean generation, compilation,
and peak memory separately. Record warm or cold Lean caches and repetitions.
Fewer variables do not guarantee a speedup. Strict time thresholds are used
only in stable environments; ordinary unit tests do not depend on incidental
wall-clock durations.
