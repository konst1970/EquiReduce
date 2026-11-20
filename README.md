# EquiReduce

**Exact symbolic reduction of equation systems with formal equivalence
proofs.** An independent Python library with SymPy input and output,
and certificate verification in Lean 4 + Mathlib.

Source repository: [konst1970/EquiReduce](https://github.com/konst1970/EquiReduce).

> Status as of 2026-11-20: release version `0.1.0` is available.
> The implementation includes the algebraic core, certificates, Lean backend,
> portable artifacts, affine coordinates, and bounded search. Lean verifies
> the 14 → 4, 4 → 3, and 14 → 3 examples. An experimental semi-explicit DAE
> API provides trajectory correspondence and chain-rule proofs.
> The implicit MNA pipeline also includes a complete Lean proof, symbolic
> initial data, partition search, and time-dependent affine charts with derivatives.
> Prescribed differentiable inputs are supported, including the full chain rule,
> explicit Lean assumptions, and exact initial value and derivative samples.
> Smooth charge laws, `exp`, explicit branches, and a concrete NPN/PNP charge
> profile are supported; implicit JSON artifacts have independent replay.

The library returns reduced equations, reconstruction formulas for eliminated
variables, validity conditions, a transformation certificate, and its verification
result. Reduction does not numerically solve the resulting system.

The first release covers algebraic systems over the real numbers. Differential-
algebraic equation (DAE) support is available through a separate experimental
API for affine algebraic blocks and supported smooth reconstruction.
The precise limits are given in the [DAE contract](docs/dae.md) and
[implicit pipeline contract](docs/implicit_dae.md).

## Documentation

[Getting started with the implemented library](docs/quickstart.md) ·
[TDD report and task status](docs/progress.md) ·
[Python API reference](docs/reference.md).

Start with the [contents](docs/index.md), [purpose and current status](docs/overview.md),
and [implementation roadmap](docs/roadmap.md).

For development, read the [detailed ER-01–ER-19 implementation plan](docs/implementation_plan.md).

- [Mathematical contract](docs/mathematical_contract.md).
- [Algebraic reduction algorithms](docs/algebraic_reduction.md).
- [DAEs: initial implementation limits and proof requirements](docs/dae.md).
- [Python library architecture](docs/architecture.md).
- [Target API](docs/api.md) and [examples](docs/examples.md).
- [Lean verification](docs/lean.md).
- [Certificate and audit artifact format](docs/artifacts.md).
- [Testing and quality criteria](docs/testing.md).
- [Development, packaging, and releases](docs/development.md).
- [Terminology and notation](docs/glossary.md).
- [Architecture decision records](docs/decisions.md).

## Building the documentation

Clone the standalone repository and install the local package for the API
reference; Lean and Mathlib are not required to build the documentation:

```bash
git clone https://github.com/konst1970/EquiReduce.git
cd EquiReduce
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,docs]'
.venv/bin/python -m sphinx -n -W --keep-going -b html docs docs/_build/html
```

Open `docs/_build/html/index.html`. You can also read the Markdown files
directly on GitHub or in an editor without building them.

The availability of the distribution name `equireduce` must be checked before
publication.

## License

EquiReduce is distributed under the [MIT License](LICENSE).
Copyright (c) 2026 konst1970.
See [code provenance](PROVENANCE.md) for the origin of extracted code.
Third-party dependencies retain their own licenses.
