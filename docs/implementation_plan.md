# Detailed EquiReduce implementation plan

Date: 2026-11-19. Status: implementation follows TDD.

This document turns the [roadmap](roadmap.md) into a sequence of verifiable
tasks. Current ER task statuses and validation evidence are kept in the
[progress report](progress.md). Dnipro prototypes are source material,
not an already completed independent library.

## 1. Expected result

The first `0.1.0` release must provide an independent Python package that:

1. Accepts an algebraic system, unknowns, parameters, and conditions as SymPy objects.
2. Performs exact scalar and block affine elimination.
3. Returns a reduced system, full reconstruction, and explicit restrictions.
4. Independently verifies the certificate and runs Lean when requested.
5. Exports a reproducible proof bundle and can be installed from a wheel.

`System.algebraic` rejects derivatives. DAEs have a separate experimental API
and their own trajectory theorems. Fully automatic coordinate search is not
a prerequisite for the first release.

## 2. Order and dependencies

Main sequence:

```text
M0: fix the contract
  ↓
M1: independent algebraic core
  ↓
M2: actual Lean proof + artifacts + release 0.1.0
  ↓
M3: coordinates, search, Dnipro adapter
  ↓
M4: semi-explicit index-1 DAEs
  ↓
M5: derivatives of eliminated variables and further extensions
```

Within M2, first bring a small end-to-end example to actual Lean compilation,
then extend the exporter and artifact format. An exploratory check of the
simplest DAE theorem can follow that example to estimate M4 complexity early.
It does not change the first release's scope.

## 3. M0 — preparation for extraction

Before coding:

- Fix the initial API contract and minimum SymPy subset.
- Map Dnipro modules to the new EquiReduce modules.
- Preserve exact input data, conditions, and expected regression results.
- Establish code and material provenance and terms for extraction.
- Separate technical acceptance from package publication: license, name
  availability, and release metadata must be finalized before external release
  rather than replaced with assumptions.

Each following task uses `todo`, `in_progress`, `blocked`, or `done` status.
Blockers and completion evidence are retained with the task. All ER tasks
initially had `todo` status; current statuses are maintained in the report,
not inferred from the existence of a description in this plan.

## 4. M1 — independent algebraic core

| ID | Work | Depends on | Completion criterion |
|---|---|---|---|
| ER-01 | Package skeleton: `pyproject.toml`, `src/equireduce`, exceptions, `py.typed`, tests, and CI | M0 | Wheel installs in a clean environment; import requires neither Dnipro nor Lean |
| ER-02 | Immutable `System`, exact residuals, unknowns, parameters, and validation | ER-01 | Tests cover empty, rectangular, and invalid inputs; derivatives are explicitly rejected |
| ER-03 | Conditions, domains, three-valued checks, and coverage | ER-02 | Division preserves excluded zeros; unknown is not reported as proved |
| ER-04 | Scalar affine elimination and reconstruction composition | ER-03 | Multiple variables are eliminated without cycles; all conditions reach final coordinates |
| ER-05 | Certificate, independent verifier, `ReductionResult`, and `reduce_system` | ER-04 | Invalid steps are rejected; valid results contain full reconstruction |
| ER-06 | Exact block elimination | ER-05 | Invertible blocks reduce; singular and undetermined blocks are not treated as invertible |

### ER-01 — minimal skeleton

Create only necessary modules, without empty DAE implementations. Configure
Ruff, type checks, and pytest. Limit initial public exports to the agreed API
so that extracting internal functions does not accidentally make them stable
external interfaces.

### ER-02 and ER-03 — data before algorithms

Validate unknown order and uniqueness, declaration of all parameters, the real
domain, exact numbers, and absence of unsupported nodes. Preserve input before
transformation; reject `Float` by default.

Separate input assumptions from added conditions. For `ay-b=0`, do not call
`y=b/a` a global reconstruction without justifying the `a=0` branch.
Condition consistency, solution coverage, and search completeness must have
independent statuses.

### ER-04 and ER-05 — first mathematical result

First example: `ay-x=0`, `y+x-1=0`, `a != 0`; eliminate `y`.
Second: `y-x**2=0`, `f(y)+x-c=0`; preserve the exact argument `f(x**2)`.
The verifier takes a source-system snapshot and a completed certificate;
it does not trust a flag set by the reducer.

### ER-06 — extension to blocks

Start with exact square blocks. Add parametric determinants, retained nonlinear
equations, and zero output unknowns when parameter constraints remain.

**M1 output:** SymPy → verified symbolic reduction → SymPy,
without claiming a formal Lean proof.

## 5. M2 — Lean, auditing, and the first release

| ID | Work | Depends on | Completion criterion |
|---|---|---|---|
| ER-07 | Pin a separate Lean/Mathlib environment | ER-01 | A clean prepared environment compiles a control theorem with known versions |
| ER-08 | Exporter for a minimal SymPy language | ER-03, ER-07 | Exact numbers, symbols, arithmetic, conditions, and declared functions translate without loss of meaning |
| ER-09 | Scalar, sequential, and block elimination theorems | ER-05, ER-08; blocks after ER-06 | Actual Lean confirms both directions and reconstruction; meaningful mutations are rejected |
| ER-10 | Runner, statuses, and `none/generate/require` modes | ER-07, ER-09 | No hidden fallback; exit code, axioms, and source correspondence are checked |
| ER-11 | JSON AST, run reports, and reproduction bundle | ER-05, ER-10 | Exact artifact replay; input or proof changes are detected; repeat compilation is reproducible |
| ER-12 | Regressions, available API documentation, and `0.1.0` preparation | ER-01–ER-11 | Full first-release acceptance criteria pass |

### Minimal formal path

Before all of M2 is complete, establish one short working sequence:

```text
System → eliminate y → certificate → proof.lean
       → actual Lean → verified ReductionResult
```

Initial subset: real numbers, exact rational coefficients, arithmetic, integer
powers, nonzero conditions, and opaque functions. `Piecewise`, logarithms,
and roots are not declared formally supported before their own integration
tests. Unsupported export returns an explicit status; printing a similar-looking
expression does not count as success.

### ER-09 and ER-10 acceptance

- Compile with `-DwarningAsError=true`.
- Allow only a subset of standard `propext`, `Classical.choice`, and
  `Quot.sound`; no `sorryAx` or custom axioms.
- Separately reject incorrect reduced equations, incorrect reconstruction,
  and removal of necessary conditions.
- In `require` mode, unavailable tools and timeouts are explicit errors,
  not reasons to return unconfirmed success.
- Bind the new theorem to the actual SymPy input and its conditions.

### ER-11 acceptance

The safe decoder supports only the documented AST, without arbitrary code
execution. Check format versions, size limits, and symbol identity. Separate
the stable content hash from timestamps and local run-report paths.

### ER-12 acceptance: `0.1.0` readiness

- Independent wheel and sdist; installation checked in a clean environment.
- Passing algebraic matrix of positive and degenerate cases.
- Passing actual positive and negative Lean tests.
- The 14 → 4 example verified by the new pipeline on an independent SymPy
  fixture, rather than by reference to an old Dnipro log.
- At least two examples outside electronics.
- Executable implemented-API examples; Sphinx builds without warnings.
- Confirmed license, name availability, and distribution contents.

ER-12 delivers a locally ready release. Publication to PyPI or another service
is a separate action after preparing that result.

## 6. M3 — coordinates, search, and integration

| ID | Work | Depends on | Completion criterion |
|---|---|---|---|
| ER-13 | Affine coordinate charts and certificate composition | ER-09, ER-11 | Forward and inverse charts and full transport to source coordinates are proved |
| ER-14 | Bounded search, metrics, and Lean benchmark | ER-13 | Deterministic order and enforced budgets; complexity estimates are separate from measured time |
| ER-15 | Dnipro adapter and formal 4 → 3 regression | ER-13; automatic selection after ER-14 | Dnipro uses the package without a reverse dependency; the entire claimed reduction chain is checked |

Support manually specified charts first, then search a chart family.
An incomplete search must not describe its result as a global minimum.
Begin Dnipro changes after stabilizing the independent API. Remove old
mathematical code only after comparing regressions, avoiding two diverging
implementations.

## 7. M4 — first DAE class

| ID | Work | Depends on | Completion criterion |
|---|---|---|---|
| ER-16 | DAE contract, types, and early Lean trajectory theorem | ER-10; contract builds on M1 | System class, regularity, domain, and bidirectional statement fixed; simplest example compiled |
| ER-17 | Affine DAE algebraic block, reconstruction, and initial conditions | ER-06, ER-16 | Symbolic result preserves time dependencies and all obligations; inconsistent initial data is not silently corrected |
| ER-18 | Generalized DAE certificate, Lean, and acceptance tests | ER-11, ER-17 | Interval trajectory equivalence proved for the claimed class |

Initial class (current experimental refinement: rational reconstruction and
differentiable trajectories; see [ADR-007](decisions.md)):

$$\dot x=f(t,x,y,p),\qquad A(t,x,p)y+b(t,x,p)=0,$$

where the algebraic block is invertible, parameters are constant in time,
and the domain and required regularity are explicit. This class contains
no derivatives of `y`.

First end-to-end example:

$$\dot x+y=0,\qquad y=x^2
\quad\longrightarrow\quad
\dot x+x^2=0,\qquad y=x^2.$$

Check `y0 = x0**2` for specific initial data and prove interval admissibility
of reconstruction. Nonsingularity conditions cannot be checked only at the
initial time. Trajectory correspondence alone does not promise existence
or uniqueness.

Do not claim formal DAE support before ER-18. If ER-16 reveals a need to
narrow the class, first change the contract and examples rather than replacing
proof with numerical experiments.

## 8. M5 — further differential extensions

**ER-19:** support derivatives of reconstructed algebraic variables after
ER-18. For `y = phi(t, x)`, compute and prove

$$\dot y=\partial_t\varphi+\partial_x\varphi\,\dot x.$$

Criteria: Lean verifies the chain rule; nonsmooth points and introduction
of higher derivatives are explicitly handled or rejected. Time-dependent
charts, high index, and branching are separate follow-up tasks, not
automatically part of ER-19.

## 9. First working iteration

The practical starting point is ER-01–ER-05, without coordinate search or DAEs:

- [x] Create the package skeleton and independent installation.
- [x] Implement `System.algebraic` and input validation.
- [x] Implement conditions and three-valued identity recognition.
- [x] Eliminate `y` in `ay-x=0`, `y+x-1=0` under `a != 0`.
- [x] Return final SymPy residuals and reconstruction.
- [x] Verify an independent certificate in both directions.
- [x] Add a degenerate branch, unchanged result, and nonlinear function to
  the regression matrix.
- [x] Update documentation for the actually available API.

Follow this iteration with the first ER-07–ER-10 Lean path for a scalar step,
then extend to blocks and complete the release criteria.

## 10. Task completion rule

A task is marked `done` when implementation, checked mathematical conditions,
required positive and negative tests, consistent documentation, and a
reproducible result are present. Formal tasks also require an actual Lean
log, versions, and axiom auditing. Packaging tasks require a wheel check
in a clean environment.

Group changes into small focused commits: skeleton, data model, conditions,
scalar reduction, certificates, blocks, Lean, artifacts, and so on.
Passing a source-text generation test does not complete a formal proof task.

Time estimates are refined after the first working iteration and minimal
Lean path. ER-16–ER-19 have the greatest research uncertainty; start them
with short verifiable theorem prototypes.
