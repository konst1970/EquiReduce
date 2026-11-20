# Architecture decision records

This log records the project's foundational decisions. The user-approved name
is distinguished from technical decisions proposed by this specification;
those decisions may be revised before implementation with consequences recorded.

## ADR-001 — the EquiReduce name

**Status:** approved by the user, 2026-11-19.

The name refers to reduction that preserves equivalence. The target Python
import name is `equireduce`. The separate repository is
[github.com/konst1970/EquiReduce](https://github.com/konst1970/EquiReduce).
Availability of the PyPI name has not yet been checked.

## ADR-002 — independent Python package using SymPy

**Status:** direction approved; the technical contract is defined by the documentation.

Input and output are SymPy objects; the core does not import Dnipro.
Application data arrives through adapters. Consequence: replace the existing
`ResidualSystem` with a general type rather than copying it unchanged.

## ADR-003 — algebra first, then DAEs

**Status:** foundational technical decision of this specification.

The first release covers algebraic reduction. DAEs need their own trajectory
theorems, regularity assumptions, and initial conditions. Consequence: the
library name remains general, while support for classes is declared in stages
without extending guarantees from a DC example to derivatives.

## ADR-004 — conditional equivalence with reconstruction

**Status:** foundational technical decision of this specification.

Every elimination returns reconstruction and conditions. An additional condition
is not automatically a proved property of every source solution. Consequence:
coverage completeness, search completeness, and proof success are separate fields.

## ADR-005 — Lean as an external verifier

**Status:** foundational technical decision of this specification.

Lean is optional when installing the Python core, but `verified` status requires
an actual run of the pinned environment. `proof="require"` has no silent
fallback. Consequence: separate integration tests, unavailability handling,
and a reproducible proof bundle.

## ADR-006 — certificates as data

**Status:** foundational technical decision of this specification.

The certificate stores checkable mathematical steps; the audit records actual
tool execution. The portable format uses a JSON AST with an allowed set of
nodes. Consequence: hashing does not replace proof, and loading an artifact
does not execute Python code.

## Open decisions

Before implementation or release, determine the license,
distribution name availability, final JSON Schema, and minimum supported
formal export subset. The experimental DAE API and Lean abstractions are
covered by ADR-007 below. Listing these open questions does not claim that
the corresponding work has already been completed.

## ADR-007 — a narrow verified DAE class

**Status:** implemented experimentally.

The first DAE API is `DAESystem.semi_explicit`, with an explicit open interval,
differentiable real trajectories, and rational reconstruction. The initial
proposal to require and prove class `C1` was narrowed to the precise statement
of `HasDerivAt` at every point. Continuity of the derivative is not claimed
separately. This agrees with the [contract](dae.md).

This class allows reconstruction derivatives to be proved structurally using
addition, multiplication, integer powers, and inversion with explicit conditions.
Nonsmooth and nonrational reconstructions are rejected rather than relying on
implicit regularity assumptions. General time-dependent charts and high index
remain separate follow-up tasks.
