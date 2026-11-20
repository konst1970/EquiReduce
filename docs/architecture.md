# Python library architecture

## Dependencies and boundaries

Equation producer → `System` → reducer → certificate → independent verifier
→ optional Lean backend → `ReductionResult`.

The core depends on the Python standard library and SymPy. Lean and Mathlib
form an external tool environment, not a core `pip` dependency. Ordinary
library import requires neither Git, Lake, network access, nor an application
package such as Dnipro.

Circuit construction, the SPICE parser, BJT models, and numerical solvers
remain outside EquiReduce. Reduction does not automatically download Lean
or Mathlib.

## Planned structure

`0.1.0.dev0` already includes `system.py`, `result.py`, `conditions.py`,
`api.py`, `artifacts.py`, `lean.py`, `coordinates.py`, `search.py`,
`metrics.py`, `dae.py`, and private modules `_core.py`, `_lean_export.py`,
`_coordinate_lean.py`, and `_dae_lean.py`. Extracted primitives remain in
private modules with their origins recorded in `PROVENANCE.md`.
The following layout is a target for further separation, not the current tree.

This tree describes the initial implementation target rather than files
that have all already been created.

```text
EquiReduce/
  pyproject.toml
  src/equireduce/
    __init__.py
    system.py                 # immutable general system description
    result.py                 # result and statuses
    conditions.py             # domains, assumptions, obligations
    errors.py
    algebraic/
      affinity.py
      elimination.py
      coordinates.py
      search.py
      metrics.py
    certificates/
      model.py
      verify.py
      serialization.py
    backends/lean/
      expressions.py          # explicitly supported SymPy subset
      algebraic.py
      runner.py
      manifest.py
  lean/                       # pinned toolchain and Mathlib
  examples/
  tests/{unit,integration,properties,regression}/
  docs/
```

The `dae/` package and Lean trajectory theorems are added at the corresponding
stage. An absent feature must not be hidden behind an empty "successful"
backend or proof stub.

## Component responsibilities

| Component | Responsibility |
|---|---|
| `System` | Validated immutable input, coordinate order, and domains |
| Conditions | Assumption provenance, new restrictions, and consistency status |
| Reducer | Construction of exact steps and reconstruction |
| Search | Enumeration and ranking; does not determine certificate validity |
| Certificate | Data sufficient for independent step verification |
| SymPy verifier | Exact identities and structural invariants |
| Lean exporter | Translation of supported expressions and theorem generation |
| Lean runner | Specific compiler invocation, log, timeout, and status |
| Serializer | Versioned safe data format and hashing |

The verifier and reducer may share arithmetic primitives, but verification
must not simply trust a flag set by the generator. Formal compilation is a
separate verification layer.

## Data invariants

- Input is unchanged; result matrices are immutable and collections are ordered.
- Every source unknown is either retained or reconstructed.
- Reconstruction is acyclic and expressed through final coordinates.
- Conditions have provenance: input, denominator, pivot block, branch,
  coordinate transformation, or DAE reconstruction differentiation.
- All free symbols are declared; unknowns, parameters, and the independent
  variable must not be substituted for one another.
- Search, symbolic verification, and Lean compilation have independent statuses.

## Extraction from Dnipro

1. Fix regression examples for the prototype.
2. Extract mathematical types without `dnipro` imports or `domain="dc"`.
3. Replace application fields `node_order` and `branch_current_order` with
   optional external metadata that does not affect the proof.
4. Extract algorithms and verifiers while auditing assumptions and domains.
5. Extract the Lean exporter, checking expression classes with actual Lean.
6. Create a Dnipro adapter that explicitly obtains static equations and passes
   them to EquiReduce. Do not simply relabel the time domain as DC.
7. Compare results before and after extraction on the same systems.

The recommended adapter location is Dnipro, avoiding a reverse dependency
from EquiReduce. After migration, maintain one mathematical implementation
rather than two copies that change independently.

## Determinism and resources

Unknown, candidate, condition, and Lean name order is fixed. Search and
expression-size budgets are explicit. Temporary directories are unique per
run; parallel checks do not overwrite a shared proof file. Caches are keyed
by input, assumptions, versions, and proof content. A cached result is
identified as reuse of an earlier verification rather than fresh compilation.
