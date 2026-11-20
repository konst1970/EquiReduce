# Purpose and current status

## The library's task

Accept an equation system as SymPy objects, find justified exact transformations,
reduce the number of unknowns or expression complexity, and return the result
with reconstruction formulas and an equivalence proof.

The system may come from electronics, mechanics, reaction kinetics, thermal
models, or another application. The EquiReduce core must not need to know what
a particular current, force, or concentration represents.

Reduction is different from solving: the output may remain a nonlinear implicit
system for which the user chooses a separate numerical or symbolic solver.
A global minimum dimension and universal simplification of arbitrary nonlinear
systems are not guaranteed.

## Verified starting point

The independent `0.1.0.dev0` implementation in `src/equireduce` is based on this
starting point. The new pipeline compiles 14 → 4, 4 → 3, 14 → 3, two examples
outside electronics, and semi-explicit DAE trajectory correspondence theorems.
See the [TDD log](progress.md) for the current status.

The original Dnipro prototypes in `dnipro/analysis/` include affine decomposition,
scalar and block elimination, coordinate transformations, bounded search,
metrics, certificates, Lean generation, and audit artifacts. They are tied to
`dnipro.mna.residual_system.ResidualSystem` and require `domain="dc"`;
these dependencies must be removed when extracting the library.

For the BJT 14 → 4 example, theorem `mna_iff_eq2` was compiled with Lean 4.36.0
and Mathlib v4.36.0, revision
`fc4f59e577feb1a4956671bc04ac18aaaf8cd842`.
Dnipro log: `docs/eq2_from_21_derivation/out/lean_verification.log`;
machine-readable report: `lean_verification.json` in the same directory.
Compilation used `-DwarningAsError=true`.

That proof covers one structural transformation under nonzero assumptions for
two resistances, reconstructing 10 variables. It does not establish the physical
BJT laws, the 4 → 3 step, DAE support, or every branch of the Lean generator.

## EquiReduce implementation limits

| Capability | Current implementation | Limit |
|---|---|---|
| Algebraic SymPy residuals | Independent `System` | Exact real expressions |
| Affine elimination | Scalar and block steps | Explicit invertibility conditions |
| Nonlinear core | Remains opaque | No promise of solving it |
| Lean proof | Actual bidirectional compilations | Documented SymPy subset |
| Coordinates and search | Charts, budgets, metrics, benchmark | Finite declared family |
| Differential equations | Experimental semi-explicit DAEs | Rational reconstruction |
| Python package | Wheel and sdist | Public release metadata is unfinished |

## First release

- Python 3.11+; SymPy is the only required third-party core dependency.
- Finite algebraic systems over the real numbers with exact coefficients.
- Conditional affine elimination with preservation of the domain of definition.
- Certificate verification independent of search.
- Optional Lean installation, with actual compilation required for formal
  backend status `verified`.
- Documented limits, reproducible examples, and tests.

The first release excludes numerical integration, operating-point search,
approximate models, automatic reduction of arbitrary DAEs, noise models,
application-specific component laws, and a web service.

Support for complex quantities, inequalities as primary equations,
distributions, impulses, and partial differential equations is also not claimed.
