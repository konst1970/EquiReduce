# Formal verification in Lean 4

## The backend's role

SymPy constructs a reduction candidate. Lean checks a specific theorem linking
the immutable input, result, conditions, and reconstruction. The library does
not treat its own SymPy checks as an independent formal proof.

Nonlinear functions may remain arbitrary functions over the real numbers if
the structural transformation is valid for any choice of those functions.
The required identity must not be declared as an axiom, nor may essential
argument dependencies be removed to simplify the theorem.

## Supported expression language

The baseline algebraic subset in `0.1.0.dev0` includes exact numbers, real
symbols, arithmetic, integer powers, conditions, and opaque functions.
The smooth extensions for `exp` and explicit `Piecewise` regions are described
below. `log`, `sqrt`, `Abs`, and `Min/Max` are not claimed as formally supported.
Legacy syntax-printing code in the private exporter does not bypass the
public capability checks.

The composed coordinate proof checks the inverse chart and all source
equations, including the 14 → 3 regression. Experimental DAEs generate
`algebraic_equivalence`, `reconstruction_chain_rule`,
`reconstructed_rate_equivalence`, and the final `reduction_equivalence`.
The last depends on all required preceding theorems, so its axiom audit also
covers the chain rule. Derivatives use Mathlib `HasDerivAt`; admissibility
of the reconstructed trajectory follows from equality of functions in a
neighborhood of each point of the open interval.

The implicit MNA backend additionally proves normalization of source composite
rational derivatives, recovery of domains, and all source rows in
`implicit_point_transport`, followed by bidirectional `reduction_equivalence`.
Time-dependent charts add `augmented_trajectory_equivalence` and an outer
theorem with existence of coordinate trajectories and derivatives of the
inverse chart. The axiom audit covers the final theorem, which depends on
the entire composition.

Prescribed inputs are neither scalar parameters nor new unknown states.
They are supplied as separate `ℝ → ℝ` functions; `hInputRegularity` specifies
differentiability on the interval. Their `deriv` and `HasDerivAt` participate
in reconstruction and composite derivative normalization. This hypothesis
is retained in the final time-chart theorem.

Algebraic condition export uses exact rules, including sets of nonzero
denominator factors. This path does not use `Expr.equals` or standard
`Relational.simplify`, which may perform numerical probing.

Declared two-variable charge laws have an explicit `HasFDerivAt` hypothesis
with a linear map constructed from both partial derivatives. Composition with
a pair of trajectories is proved using Mathlib theorems without additional
axioms. Concrete exponentials use `HasDerivAt.exp` and exact
`Real.exp_add/sub/neg` identities. A result for a declared law is conditional
on its contract; separate concrete BJT tests use its actual formulas and do
not use `hSmooth` to stand in for the physical model.

`Piecewise` branches remain in the source formal statement. Their strict
regions are assumed throughout the interval; equality with the selected
formula near a point yields the derivative of the source function.
The three terminal charge balance and its derivative balance have actual proofs.

Formal backend support must be declared and tested incrementally: real symbols,
exact integers and rationals, arithmetic, integer powers, equalities, condition
inequalities, and arbitrary declared functions. Extensions for `exp`, `log`,
`sqrt`, `Abs`, `Min/Max`, and `Piecewise` form separate groups. Printing the
syntax does not mean that every transformation involving that function can
be proved.

Translation rules must specify:

- Domains and branches of roots and powers.
- `Piecewise` order, including the final branch and boundaries.
- Binary folding of `Min/Max` with arbitrary argument counts.
- Function assumptions and arities.
- Unambiguous name mapping without collisions with Lean keywords.
- Rejection of unsupported nodes without substituting zero or a similar-looking expression.

Ordinary derivatives and trajectory theorems belong to the separate DAE
backend. They are not exported as independent scalar variables to claim a
complete proof.

## Theorem structure

A scalar step proves equivalence between the source equation set and the
new set together with the elimination formula. A coordinate map proves
existence and uniqueness of the corresponding coordinates under chart
invertibility. The final composition proof must refer to the exact source
and final residuals.

Domain restrictions appear as hypotheses or corresponding theorem predicates.
A proof of only forward substitution is not a complete bidirectional
certificate. Absence of solutions or existence of at least one solution
requires a separate statement.

## Compilation procedure

1. Check Lean/Mathlib versions against the configuration.
2. Generate self-contained source with the exact statement and proof.
3. Record the source hash and the mapping from SymPy objects to Lean names.
4. Compile in a separate directory with `-DwarningAsError=true`.
5. Check the exit code, diagnostics, and theorem axiom list.
6. Confirm that the recorded source with the required input was checked.
7. Record the command, logs, versions, conditions, and verification result.

The command is an argument list, with `shell=False` and a time limit.
Verification itself does not automatically install tools, execute arbitrary
artifact code, or perform network operations.

The initial pinned environment for comparison with Dnipro is Lean 4.36.0,
Mathlib v4.36.0, revision `fc4f59e577feb1a4956671bc04ac18aaaf8cd842`.
This is a compatibility baseline, not a promise of support for every Mathlib
version. Toolchain changes require formal regression tests.

## Statuses

| Status | Meaning |
|---|---|
| `not_requested` | Formal verification was not requested |
| `generated` | Source exists without confirmed compilation |
| `verified` | Compilation and axiom auditing succeeded |
| `failed` | Lean rejected the proof or forbidden dependencies were found |
| `unavailable` | Required tools or prepared dependencies are missing |
| `unsupported` | Transformation or expression is outside the supported class |
| `timeout` | Verification was stopped at the time limit |

Only `verified` permits a result to be described as Lean-verified.
Failures are not replaced by successful SymPy checks.

## Axioms and the trusted boundary

The initial configuration allows only a subset of the standard axioms
`propext`, `Classical.choice`, and `Quot.sound`. `sorryAx`, `sorry`,
`admit`, and additional application-specific axioms are forbidden.
The actual dependency list is obtained from Lean for the target theorem.
Searching the source for `sorry` is useful as a preliminary check, but does
not replace compilation and dependency analysis.

The trusted boundary includes Lean/kernel, imported Mathlib, correctness of
the SymPy → Lean exporter, and correspondence between the supplied equations
and the problem. Run-report hashes prevent accidental file mismatches, but
are neither mathematical proofs nor evidence of authorship.

## Tests and caching

Runner unit tests may mock the process to exercise errors and timeouts.
They are not proofs. A separate integration group must compile actual
theorems and reject deliberately corrupted formulas.

The cache key contains the source system, conditions, certificate, Lean source,
exporter version, toolchain, and dependency revisions. Changing any component
invalidates the old success for the new result. Cache reuse is recorded in
the run report.
