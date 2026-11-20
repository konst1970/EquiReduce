# Dnipro adapter

## Time-domain DAE pipeline

`dnipro.analysis.from_time_system` accepts a time-domain `ResidualSystem`,
an optional manual `differential` / `algebraic` partition, and an open interval.
`assume_real=True` explicitly chooses a real domain for legacy Dnipro labels.
It provides an immutable source snapshot with metadata, a symbol map, and
row provenance.

`adapter.analyze()` calls EquiReduce structural analysis; `adapter.reduce()`
performs implicit algebraic elimination. Derivatives are retained.
`adapter.restore_expression` and `restore_reconstruction` return original
Dnipro labels. The contract and symbolic verification limits are described
in the [implicit API](implicit_dae.md).

From the Dnipro root:

```bash
python -m examples.dae_pipeline rc
python -m examples.dae_pipeline rl
python -m examples.dae_pipeline rlc
python -m examples.dae_pipeline rc --auto --initial-zero --proof require
python -m examples.dae_pipeline rl --chart-time --proof require
python -m examples.dae_inputs --proof require
```

These examples neither integrate the system nor find a numerical operating point.

`adapter.reduce(auto=True, preferred_differential=(...), max_candidates=32)`
performs budgeted search. If the partition is omitted when creating the
adapter, all variables are initially retained. A manual partition, when
specified, must include both parts.

`initial_time`, `initial_values`, `initial_rates`, and `parameter_values`
accept original Dnipro labels and are transported exactly through `symbol_map`.
`initial_check` distinguishes symbolic obligations from proved pointwise
consistency, without guaranteeing existence of a solution.

`adapter.coordinate_transform(variables=..., matrix=..., offset=...)`
creates a time-dependent chart. `adapter.reduce_in_coordinates(chart,
differential=..., algebraic=...)` returns reconstruction of original states
through new coordinates. Nonsingularity holds throughout the interval;
matrix and offset derivatives are included.

For time-domain DAEs, `inputs=(u, ...)` explicitly declares prescribed real
differentiable functions. Their samples are passed through
`initial_input_values={u: ...}` and
`initial_input_rates={Derivative(u, t): ...}` using original Dnipro labels.
These arguments work with manual/automatic elimination and time-dependent
coordinates. `examples.dae_inputs` builds actual time-domain MNA from
`VoltageSource(source_value=u)`, retains $\dot u$ in reconstruction, and checks
the entire transition in Lean with explicit input regularity.

## Single-call API and time-pipeline CLI

From the Dnipro root after installing both packages:

```python
from pathlib import Path
from equireduce import LeanConfig
from dnipro.analysis import reduce_time_system, load_time_artifact

pipeline = reduce_time_system(
    "V1 in 0 U0\nR1 in out R\nC1 out 0 C",
    interval=(-1, 1), retain=("v_out",), assume_real=True,
    proof="require", lean=LeanConfig("EquiReduce/lean"),
)
equations = pipeline.equations             # tuple SymPy Eq, original labels
reconstruction = pipeline.reconstruction   # original labels
native = pipeline.reduction               # exact EquiReduce result and certificate
path = pipeline.export(Path("proofs/rc"))
restored = load_time_artifact(path)
```

Input may be a `Circuit`, time-domain `ResidualSystem`, netlist text, or a
file `Path`. `retain` specifies function names to keep. For manual elimination,
set `auto=False`; explicit `differential` and `algebraic` may be supplied.
`time` specifies a real clock; prescribed inputs are bound through
`input_sources={"V1": u}` without modifying the supplied circuit object.
Initial data and verification parameters use the same call.
`provenance` retains an immutable snapshot, symbol map, row names, physical
model conditions, branch choices, and explicit real-domain policy.
Independent EquiReduce can load this artifact without importing Dnipro.

```bash
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real \
  --proof require --lean-project EquiReduce/lean --artifact proofs/rc
dnipro verify-dae proofs/rc --lean-project EquiReduce/lean
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output json
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output latex
dnipro dae examples/dae_rc.cir --interval -1 1 --retain v_out --assume-real --output lean
```

`--output lean` generates a proof; only `--proof require` compiles it.
`verify-dae` always repeats symbolic verification; with `--lean-project` it
performs fresh compilation, otherwise it marks the earlier run report as
`recorded`. `--manual`, `--max-candidates`, and `--max-minors` control block
selection. `--input-source V1=u`, `--initial-time 0`, `--initial v_out=2`,
`--initial-input u=3`, `--initial-input-rate u=5`, and `--initial-param R=1`
specify exact samples; the last option applies to initial checking and does
not change equations for the whole trajectory. Decimal literals and SPICE
suffixes are parsed as exact rational numbers. The `dae` command has no
numerical solver or `--numeric` option.

## Concrete charge-based BJT

```bash
dnipro dae examples/dae_bjt.cir --interval -1 1 --list-branches
dnipro dae examples/dae_bjt.cir --interval -1 1 --retain v_b --retain v_c \
  --assume-real --branch 0:0 --proof require --lean-project EquiReduce/lean \
  --artifact proofs/bjt
```

`--branch POSITION:INDEX` refers to the deterministic `--list-branches` list.
In Python, `branch_choices` accepts that index map or `(Piecewise, index)`
pairs. Without an explicit complete branch choice, the pipeline rejects
`Piecewise`. The choice applies throughout the interval.

`build_equations(..., preserve_charges=True)` retains `Derivative(Q,t)` for
chain-rule verification. The new single-call API enables this mode.
The default legacy equation-building mode is unchanged. Metadata includes
physical BJT domain conditions, including a positive Early factor.
The example uses exact normalized parameters, fixed `VT`, `MJE=MJC=0`,
nonlinear `TF/TR` charge, and Early effect. Both polarities and both branches
have been checked. This does not claim all BJT options: graded junctions with
noninteger powers, general quasi-saturation, and switching events are outside
the declared formal profile.

DN-DAE-10–12 acceptance: 254 library tests, 557 Dnipro regressions for analysis,
MNA, parser, export, CLI, and circuit, plus a separate final run of 10 API/CLI
tests after the LaTeX fix. Checks include a standalone wheel without Dnipro,
replay of old artifacts and a concrete BJT, and fresh RC/BJT compilations
through installed `verify-dae`.

## DC and stationary projection

The adapter lives in Dnipro at `dnipro/analysis/equireduce_adapter.py`.
EquiReduce does not import Dnipro. Dnipro now explicitly depends on
`equireduce==0.1.0.dev0`; install both local projects together:

```bash
python -m pip install -e ./EquiReduce -e .
```

```python
from dnipro.analysis.equireduce_adapter import from_dc_system

adapter = from_dc_system(residual_system, assume_real=True)
result = adapter.reduce()
original_labels = adapter.restore_reconstruction(result)
```

`from_dc_system` accepts only `domain="dc"`. Unknown Dnipro assumptions do
not silently become real: `assume_real=True` explicitly selects the real
domain, and `real_domain_assumed` records its use. Symbols known to be
nonreal are rejected. Source lists and symbols are unchanged. `symbol_map`
shows label correspondence; parameters are inferred from free symbols in
the system and conditions.

Time-domain models have a separate operation:

```python
from dnipro.analysis.equireduce_adapter import stationary_from_time

adapter = stationary_from_time(time_system, assume_real=True)
assert adapter.origin == "stationary"
```

It zeros only declared first state derivatives and constructs steady-state
equations. Domains are read before zeroing: `x′/(x-1)` retains `x != 1`.
External time dependence, unknown derivatives, and higher derivatives are
rejected. State sign assumptions are retained; imaginary states are not
reinterpreted as real.

The projection certificate applies to the resulting algebraic system.
Time-trajectory correspondence uses a separate `DAESystem` with the
[DAE contract](dae.md).

`dnipro.analysis.reduction` is now a compatibility layer: it preserves the DC
domain, result schema, legacy symbol identity, and Dnipro exceptions.
Elimination, affine decomposition, and trace verification delegate to the
shared EquiReduce core. Duplicate algorithms have been removed. For this
development version, the bridge uses a pinned private core format; dependency
version updates require compatibility validation.

The legacy interface retains historical symbols without silently changing
their identity; the new explicit real-domain contract is available through
`from_dc_system`. The legacy interface now also preserves source poles and
allows elimination of a separate affine subblock while retaining a nonlinear
residual. This may yield stronger reduction than the previous implementation.
Comparative regressions cover contracts, certificates, search, coordinates,
metrics, artifacts, and Lean generator compatibility.
