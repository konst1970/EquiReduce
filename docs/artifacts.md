# Certificates, serialization, and auditing

## Three distinct objects

1. **Reduction certificate** — mathematical data for checking the transformation.
2. **Lean source** — a specific formal statement and its proof.
3. **Run report** — what was checked, when, with which command and version.

A successful run report without the corresponding source and input is
insufficient for reproduction. A certificate without compilation has only
symbolic verification.

## Certificate contents

- Source residuals, coordinate order, parameters, and domain of definition.
- Final residuals, coordinate maps, and reconstruction in source order.
- Input and additional conditions with provenance and branch coverage status.
- Each step: type, row indices, pivot coefficients, substitution, invertibility
  obligations, and connection to subsequent residuals.
- Bidirectional linear row-combination matrices, when available.
- Algorithm version and serialization schema.

Optional search information must not affect mathematical certificate validity.
Verification accepts a completed candidate without searching again for the best one.

## Safe SymPy format

The public portable format is JSON with a versioned expression tree.
`str(expr)` and `srepr(expr)` may be included for readability, but are not
the sole reconstructible representation.

The decoder supports only an explicit list of nodes: symbol, integer, rational,
sum, product, supported power, registered function, predicate, and supported
conditional branch. DAE nodes are added through a separate capability version
with derivative order and independent-variable checks.

Example rational-number node:

```json
{"type": "Rational", "numerator": "1", "denominator": "3"}
```

Numerators and denominators are encoded as arbitrary-precision decimal strings.
Symbols have stable IDs and assumptions: two variables with the same printed
name but different assumptions must not be merged. Undefined function names
and arities are stored in a separate registry.

Public loading does not use `pickle`, `eval`, `exec`, or unrestricted `sympify`
on artifact text. The decoder bounds tree depth, node count, matrix dimensions,
and numeric sizes; unknown nodes or newer incompatible schemas are rejected
with `ArtifactError`.

## Container schema

The initial schema identifier is `equireduce.reduction/v1`.
The implemented container has these fields:

| Section | Data |
|---|---|
| `schema` | `equireduce.reduction/v1` |
| `payload` | Typed AST of the complete `ReductionResult` |
| `sha256` | Checksum of the entire payload, including the run report |
| `mathematical_sha256` | Separate stable hash of the mathematical certificate |
| `versions` | Python, SymPy, EquiReduce, and exporter version |

`payload` stores `source`, `reduced_system`, conditions, reconstruction,
`certificate`, `symbolic_check`, and `formal_check`. The last of these also
contains the Lean version, Mathlib revision, command, UTC timestamp, duration,
exit code, and log. After loading, `formal_check.origin="recorded"`.

The machine-readable schema is implemented in
`src/equireduce/resources/artifact-v1.schema.json` and tested with a JSON Schema
2020-12 validator. Shape validation is supplemented by certificate, domain,
reconstruction, and coverage metadata checks during loading.

## Canonicalization and hashes

Stable content uses UTF-8 JSON with fixed object key order and separators,
preserving array order. Symbol names are not normalized in a way that changes
their identity. NaN and infinite JSON numbers are not allowed.

Runtime, absolute local paths, and machine characteristics are excluded from
the stable mathematical hash. They are retained in a separate run report,
which can also have its own hash.

In `v1`, this distinction uses `mathematical_sha256` and `sha256`:
the latter intentionally changes when the run report changes.

SHA-256 detects content changes but is neither an author signature nor a
correctness proof. Even an artifact with a matching hash needs certificate
verification or fresh Lean compilation for the corresponding trust level.

## Reproduction bundle

The implemented directory export contains:

```text
artifact.json
proof.lean
verification.json
verification.log
lean-toolchain
lakefile.toml
lake-manifest.json
README.md
```

Downloaded `.lake` dependencies, temporary files, and the local Python
environment are excluded. Instructions must distinguish initial dependency
download from repeat verification in an already prepared environment.

For DAEs, the bundle additionally retains the time domain, regularity,
derivative reconstruction, and initial data handling. An algebraic run report
cannot replace this information.

The current schema root is `Result` or `DAEResult`. Composed coordinate
certificates retain both maps and the inner trace. The semi-explicit contract
uses first derivatives of declared states. DAE loading also recomputes right-hand
sides, reconstruction derivatives, and initial data status. The development
schema has changed; compatibility with arbitrary old experimental files is
not a stable-release promise.

## Implicit DAEs: a separate schema namespace

The new pipeline uses `equireduce.implicit/v1` and
`artifact-implicit-v1.schema.json`, with root `ImplicitResult`.
The AST supports first derivatives of composite charge expressions, explicit
`Piecewise` pairs, smooth law declarations, normalization, the mass matrix
and rank report, both time-dependent maps, initial input samples, source row
indices, and the partition selection report.

Loading:

1. Checks the version, size, structural limits, and both hashes.
2. Independently verifies the certificate, chain rule, branches, and domains.
3. Reconstructs every mathematical result field without repeating elimination.
4. Rechecks initial values, missing inputs, and obligations.
5. Checks the search report against its declared finite family and candidates.
6. Verifies the pure renaming of source labels when `provenance` is present.
7. Checks the Lean source and hash, retaining the run report as `recorded`.

Changes to coverage, equations, derivatives, rank, initial status, or source
labels are rejected even with a recomputed overall SHA-256.
Provenance confirms correspondence between the snapshot and mathematical
input, not authorship or physical correctness of the model.

Replay limits: JSON up to 2 MB, up to 100000 AST nodes, depth up to 64,
up to 512 recorded search candidates, and a rank budget of up to 4096 minors.
Unknown records, tags, operator functions, and excessive powers are rejected.
Arbitrary strings are never parsed as SymPy/Python code.

`artifact_document(result)` in `equireduce.artifacts` returns the same complete
AST for CLI JSON output without an intermediate file.
