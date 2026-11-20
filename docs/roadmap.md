# Implementation roadmap

This roadmap defines the original milestone order and completion criteria,
without calendar deadlines. M1 is implemented and the main engineering scope
of M2 works in `0.1.0.dev0`; release decisions and subsequent milestones are
tracked in the [progress report](progress.md), including completed extensions.

The [detailed implementation plan](implementation_plan.md) contains ER-01–ER-19,
dependencies, completion criteria, and the first working iteration.
This page remains a short milestone roadmap.

## M0 — agree on the contract

Deliverable: this documentation set, an explicit algebra/DAE boundary,
a definition of conditional equivalence, the target API, and acceptance criteria.

Before extracting code, confirm licensing and material provenance.
Optional future capabilities do not block the first MVP.

## M1 — independent algebraic core

Work:

- Create `pyproject.toml`, `src/equireduce`, tests, and basic CI.
- Implement general `System`, `ReductionResult`, conditions, and exceptions.
- Extract affine analysis and scalar and block elimination.
- Implement full reconstruction and an independent certificate verifier.
- Introduce exact numbers, domain preservation, and three-valued checks.

Complete when the library works without Dnipro, accepts general SymPy systems,
correctly returns an unchanged result when no supported steps exist, and passes
positive and degenerate algebraic examples. Derivatives are explicitly rejected
at this stage.

## M2 — formal algebraic backend and auditing

Work:

- Extract and validate the exporter for the supported SymPy subset.
- Pin Lean/Mathlib and implement the runner and axiom auditing.
- Support `none`, `generate`, and `require` without hidden fallback.
- Implement a safe JSON format and reproduction bundle.
- Compile new-pipeline results for 14 → 4 and systems outside electronics.

Complete when actual Lean tests accept correct transformations, reject
deliberate errors, and do not allow an unrelated run report or changed proof
to be presented as a current verification.

**First `0.1.0` release candidate = M1 + M2**, including all general testing
and packaging criteria. Universal DAE reduction and complex automatic search
are not prerequisites.

## M3 — coordinates, search, and Dnipro integration

Work:

- Extract affine charts and bounded deterministic search.
- Prove composition of the chart and elimination back to the source system.
- Add metrics and actual Lean benchmark runs.
- Create a Dnipro adapter and remove duplicate mathematical code.
- Formally close 4 → 3 with a separate proof from the new pipeline.

Complete when search completeness is correctly restricted to the declared
family, results depend only on explicit input and parameters, and Dnipro
reproduces earlier examples through the independent package.

## M4 — experimental index-1 DAE support

Work:

- Agree on `DAESystem` and the representation of time, functions, and initial data.
- Restrict support to a semi-explicit class with an affine invertible algebraic block.
- Formalize regularity, interval domains, and initial consistency.
- Implement reconstruction and independent DAE certificates.
- Compile Lean trajectory equivalence theorems.

Complete when positive examples have actual bidirectional interval proofs,
while high index, domain violations, and inconsistent initial conditions are
explicitly rejected. Do not claim DAE support before this criterion is met.

## M5 — DAE extensions

Possible work after M4 includes derivatives of reconstructed algebraic variables,
the chain rule, time-dependent coordinate transformations, bounded branching,
and selected higher-index classes. Each class gets its own contract, domains,
limits, and formal tests.

Automatic reduction of arbitrary index, nonsmooth events, hybrid systems,
PDEs, and approximate models are not automatically included. Supporting them
requires a separate decision and scope estimate.

## Initial concrete step

Start M1 by creating the Python package skeleton and a general algebraic system
type, then extract scalar affine elimination with reconstruction verification.
Do not start by copying all of `dnipro/analysis` or promising support for
arbitrary DAEs.
