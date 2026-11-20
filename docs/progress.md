# Plan progress and TDD log

Date: 2026-11-20. Version: `0.1.0.dev0`.

Update, 2026-11-20: integration stages DN-DAE-01–12 are implemented — the
implicit contract, Dnipro time adapter, exact derivative/rank analysis,
algebraic elimination without mass matrix inversion, complete Lean proof,
symbolic initial data, budgeted partition selection, time charts, and prescribed
differentiable inputs with the full $\varphi_u\dot u$ term; smooth charges
and exponentials, explicitly selected open BJT branches, a single API/CLI,
and portable implicit JSON artifacts.
The current contract and limits are in the [implicit API](implicit_dae.md).
The BJT profile is restricted to fixed VT, MJE=MJC=0, TF/TR, and Early effect;
this does not formalize every transistor model option.
The historical ER results below refer to the previously implemented subset.

## Task status

| Task | Status | Result |
|---|---|---|
| ER-01 | done | Independent `src` package, types, packaging, and CI template |
| ER-02 | done | Immutable `System`, exact numbers, and domain validation |
| ER-03 | done | Conditions, sign assumptions, coverage, and three-valued checks |
| ER-04 | done | Scalar elimination and reconstruction composition |
| ER-05 | done | Separate certificate verifier and public API |
| ER-06 | done | Invertible affine blocks, parametric conditions, and nonlinear residuals |
| ER-07 | done | Separate pinned Lean 4.36.0 / Mathlib environment |
| ER-08 | done | Minimal formal SymPy subset; other operations are explicitly rejected |
| ER-09 | done | Scalar, sequential, and block bidirectional proofs; new 14 → 4 example |
| ER-10 | done | Actual runner, proof modes, axiom audit, hashes, and logs |
| ER-11 | done | JSON AST, machine-readable schema, integrity checks, and reproduction bundle |
| ER-12 | in_progress | Technical version works; license and public release metadata are undecided |
| ER-13 | done | Affine charts, independent composition checks, and complete Lean proof |
| ER-14 | done | Deterministic budgeted search, metrics, and actual Lean measurements |
| ER-15 | done | Adapter, stationary projection, formal 4 → 3 / 14 → 3; the old DC reducer delegates to the shared EquiReduce core |
| ER-16 | done | Experimental semi-explicit DAE contract and actual trajectory theorem |
| ER-17 | done | Affine algebraic block, rational reconstruction, and initial data |
| ER-18 | done | DAE certificate, JSON, and bidirectional Lean theorem on an open interval |
| ER-19 | done | Rational chain rule and checked first-rate substitution on the reconstruction graph |

ER-16–ER-19 are complete for a narrow experimental class: differentiable
trajectories, rational reconstruction, and an invertible square affine
algebraic block. This is not general reduction of arbitrary DAEs or a separate
continuity theorem for a `C1` derivative. The contract refinement is recorded
in [ADR-007](decisions.md).

The GitHub CI template targets a future separate repository. The nested
workflow does not run automatically in the current Dnipro repository;
GitHub runs are not counted as completed. Python 3.13 was checked locally;
other versions have not yet been run in CI.

## How TDD was performed

1. System and reduction tests were added first. The initial run failed with
   `ModuleNotFoundError` because `equireduce` did not yet exist.
2. A minimal independent pipeline brought 29 tests to green. A nonlinear
   residual test exposed an affine subblock search bug.
3. Red tests for the formal API were followed by actual Lean compilations.
   Normalization differences in sequential substitutions and parametric
   blocks were corrected in the proof generator.
4. Red tests covered the JSON API, mathematical hash, forged coverage,
   expression structure preservation, and machine-readable JSON Schema.
5. Sign-assumption counterexamples showed that a positive variable could be
   reconstructed as negative. SymPy assumptions are now included in the
   domain; discrete assumptions are explicitly rejected.
6. Different `PYTHONHASHSEED` values exposed unstable Lean names for symbols
   sharing a printed name. Generation order was made deterministic.
7. After green, formatting and type checks were added, along with independent
   formal regressions for 14 → 4, flow balance, and geometry.
8. Red coordinate tests required reconstruction of source variables, rejection
   of a forged inverse chart, and trace composition. Lean then also checked
   parametric determinants, offsets, and arbitrary function argument normalization.
9. Red search tests exposed incorrectly marking an incomplete report complete
   or benchmarking it for another system. Reports are now tied to their
   source, family, and budget.
10. For 14 → 3, the independent verifier found a normalization discrepancy in
    intermediate substitutions, corrected before Lean compilation.
11. Red adapter tests required an explicit real domain and separate stationary
    projection. Further counterexamples checked sign preservation and
    rejection of an imaginary state.
12. Initial DAE tests failed because the API was absent. After symbolic
    implementation, actual Lean tests covered polynomial, time-dependent,
    and parametric reconstruction, a coupled block, and an arbitrary right-hand side.
13. A negative Lean test replaces derivative coefficient `2` with `3`;
    the compiler rejects the proof. Red pole tests showed that domains must
    be read before replacing functions with algebraic symbols.
14. DAE artifacts check derivatives and initial data even after the transport
    hash of a forged file is recomputed.
15. Red regressions before switching Dnipro showed that the old algorithm
    blocked affine subblock elimination because of a nonlinear row and lost
    a source-expression pole. Dnipro now delegates to EquiReduce; the old
    algorithms were removed and the DC result schema retained. One old test
    was refined: a nonlinear row cannot serve as an affine pivot, but does
    not prevent reduction using a separate linear row.
16. Red smooth-charge tests required explicit partial derivatives, exponentials,
    and raw `Piecewise` preservation. Actual Lean proofs cover both claimed
    NPN/PNP branches and three-charge balance. Deliberately losing a mixed
    derivative is rejected by the kernel.
17. Red tests for new JSON, API, and CLI functionality check independent replay,
    original labels, an explicit clock, and prescribed inputs. Forged structure,
    initial data, coverage, and source snapshots are rejected even after
    recomputing the transport hash.

## Confirmed checks

```text
.venv/bin/python -m pytest -q
254 passed; no skips in the prepared Lean environment

.venv/bin/python -m ruff check src tests examples
All checks passed

.venv/bin/python -m mypy src/equireduce
Success: no issues found in 29 source files
```

Tests include actual Lean compilations; a deliberately wrong final equation
is rejected by the compiler. Every successful formal result audits axioms,
not only the process exit code. Hypothesis additionally checks small exact
rational blocks. The 557 Dnipro regressions passed for analysis, MNA, parser,
export, CLI, and circuit. After the final LaTeX fix, all 10 new API/CLI tests
were rerun (one was added after collection of the full run).
New tests include the time adapter, RC/RL/RLC, a prescribed input, both NPN/PNP
branches, and the end-to-end API/CLI. External SPICE runs are excluded from
symbolic acceptance.

DN-DAE-09 checks include the full $\varphi_u\dot u$ term for multiple inputs,
domain preservation and explicit Lean regularity, initial samples and missing
samples, and composition with search and time charts. Zeroing the input
derivative is rejected by the actual kernel. A test forbids numerical probing
also during formal source generation. A condition simplification change exposed
a discrepancy in an older polynomial coordinate proof; its two levels were
aligned using exact rules, and the full suite passed again.

Actual examples are retained in ignored `examples/output/`: `bjt143` contains
the complete 14 → 3 proof, and `dae-first-order` the trajectory correspondence
and chain-rule proof. Reproduction scripts are included in the source
distribution. New `rc-pipeline` and `bjt-dae-npn` bundles were obtained through
the installed CLI; both artifacts were recompiled with `verify-dae`.

The benchmark actually measured three coordinate candidates. Local score/time
correlation was `-1.0`; this does not confirm universal predictive quality.
Timing and statuses are separate from deterministic symbolic metrics.

Wheel and sdist build successfully, and `twine check` accepts both.
The wheel was installed with dependencies into a new `/tmp` directory and
checked using `python -I -S` outside the checkout: Dnipro was unavailable,
while import, reduction, Lean generation, and complete artifact replay worked.
A smooth `Piecewise` and a concrete BJT artifact with a source snapshot were
also restored without importing Dnipro. The wheel contains `py.typed`, JSON
Schema, and pinned Lean configuration; caches, virtual environments, and Dnipro
code are excluded.

## Current version limits

- Search is optimal only among evaluated charts of the declared family.
- Implicit DAEs are limited to the [contract](implicit_dae.md): smooth
  reconstruction, rational time charts, first derivatives, and explicit branches.
  High index, arbitrary nonlinear elimination, noninteger dynamic powers, and
  branch transitions are unsupported.
- The formal backend does not claim support for every SymPy operation.
- `generated`, `verified`, and historical JSON results are distinguished.
- Conditional reduction is not described as complete source-solution coverage.
- No numerical solver or integrator is added.
- The implementation did not publish a release or create automatic Git commits.

The remaining original-plan work is the release part of ER-12: decisions on
licensing, name availability, and public release metadata. Technical stages
are complete within the documented support limits. The package remains
`0.1.0.dev0`, unpublished.
