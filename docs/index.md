# EquiReduce documentation

**EquiReduce** is an independent Python library for exact reduction of SymPy
equation systems and formal equivalence verification in Lean 4.

Development version `0.1.0.dev0` provides algebraic reduction, coordinate charts,
bounded search, and semi-explicit and implicit DAEs with trajectory proofs.
Current validation results and unfinished work are listed in the
[progress report](progress.md). Start with the [practical guide](quickstart.md).

Recommended reading order: purpose → mathematical contract → algorithms →
API → Lean → testing → implementation plan. For derivatives, also read
the DAE section.

```{toctree}
:maxdepth: 2
:caption: Specification and development

overview
quickstart
progress
mathematical_contract
algebraic_reduction
coordinates
dae
implicit_dae
dnipro
architecture
api
reference
examples
lean
artifacts
testing
development
roadmap
implementation_plan
decisions
glossary
```
