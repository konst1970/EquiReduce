# Development, packaging, and releases

## Current status

The directory contains the `src/equireduce` package, tests, packaging, and a
Lean environment. Use local installation with `pip install -e '.[dev,docs]'`.
The public distribution name has not yet been checked; `pip install equireduce`
without a local path does not install this working version.

## Python package

- Python 3.11+; import name `equireduce`.
- `src` layout; metadata and tool configuration in `pyproject.toml`.
- PEP 517/518/621; initial build backend `setuptools`.
- Required core dependency: `sympy>=1.14,<2`; each supported range must be
  tested, starting with SymPy 1.14.0.
- Extras: `dev` for pytest, Hypothesis, Ruff, mypy, build, and twine;
  `docs` for Sphinx and MyST. Lean is not installed through an extra.
- Public API annotations, `py.typed`, and NumPy-style Python docstrings.
- Identifiers, docstrings, comments, messages, and project documentation are
  written in English. Sphinx uses the English locale.

Version `0.1.0` is intended for the first accepted algebraic release;
this documentation does not declare that release published.
Before 1.0, incompatible API changes are recorded in `CHANGELOG.md` and the
minor version. Certificate formats have separate schema versions.

## Style and change structure

Ruff rules: `E`, `F`, `I`, `UP`, `B`, `SIM`, with line length 88;
format using `ruff format`. Public mathematical types use immutable
dataclasses, tuples, and immutable SymPy matrices. Broad `except Exception`
without diagnostics and hidden approximation are forbidden in the mathematical
pipeline.

Every new transformation includes a theorem statement, validity conditions,
an example, a counterexample violating the conditions, a certificate, and
appropriate tests. Default logging does not print large expressions;
diagnostics are available through structured results and an explicit verbosity
level.

## Developer environment after package creation

Workflow from the EquiReduce root:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev,docs]'
.venv/bin/python -m ruff check src tests
.venv/bin/python -m ruff format --check src tests
.venv/bin/python -m mypy src/equireduce
.venv/bin/python -m pytest -m 'not lean'
.venv/bin/python -m sphinx -n -W --keep-going -b html docs docs/_build/html
```

Sphinx autodoc imports the local package for the API reference.
Installing `.[docs]` includes the core and SymPy; Lean is not required for
documentation. `docs/requirements.txt` contains only Sphinx and MyST.

The standalone repository is [konst1970/EquiReduce](https://github.com/konst1970/EquiReduce).
Its `.github/workflows/ci.yml` runs on pushes and pull requests, with Python
3.11/3.13 checks and a separate pinned Lean job. CI downloads the derivative
product and exponential modules required by smooth charge proofs.
Dnipro adapter tests are optional integrations: without a parent Dnipro checkout,
those tests explicitly skip; the independent mathematical tests still run.
Actual hosted results are available on the repository Actions page.

HTML supports formulas through MathJax; the default Sphinx configuration
loads it from a CDN when viewing pages. Offline publication requires a local
copy of MathJax with a pinned version. This does not affect building the
textual HTML documentation itself.

## Lean environment after extraction

The separate `lean/` directory contains `lean-toolchain`, `lakefile.toml`,
and `lake-manifest.json`. The initial toolchain and Mathlib revision are
specified in the [backend specification](lean.md).

After creating that directory:

```bash
cd lean
MATHLIB_NO_CACHE_ON_UPDATE=1 lake update
lake exe cache get
cd ..
.venv/bin/python -m pytest -m lean
```

The initial download requires network access. For a small import set, download
only the required cached modules rather than all of Mathlib.
The library does not install dependencies during ordinary reduction.

## License and code provenance

Before publication, choose an EquiReduce license and confirm permission to
extract source code and examples from Dnipro and other materials.
The absence of `LICENSE` does not grant permission to declare someone else's
material MIT-licensed. Preserve SymPy, Lean, Mathlib, and transitive component
licenses according to their terms. Dependency source is not copied into the
package unnecessarily; `.lake` is not published.

The repository address is https://github.com/konst1970/EquiReduce.
Availability of the public PyPI distribution name `equireduce` must still be
checked before a package release; publishing source to GitHub does not publish
a PyPI distribution or assign a distribution license.

## Packaging and release

After meeting the [readiness criteria](testing.md):

```bash
.venv/bin/python -m build
.venv/bin/python -m twine check dist/*
```

Install the wheel in a clean environment without a Dnipro checkout, editor
paths, or Lean. Check import, ordinary algebraic reduction, and a clear failure
when formal verification is requested without Lean.

The package contains Python code, `py.typed`, a license, and required formal
backend templates. Test results, local caches, virtual environments, and large
benchmark artifacts are excluded from the wheel.

Publication to PyPI, GitHub Releases, or another service is a separate action
after preparing a verified release. This documentation does not perform it.
