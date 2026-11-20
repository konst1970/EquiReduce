# Code provenance

The affine reduction primitives in `src/equireduce/_core.py` and the initial
exporter in `_lean_export.py` were adapted from the Dnipro prototype
(`dnipro/analysis/reduction.py` and `lean_reduction.py`, repository commit
[`f634f73d2880fb1f57b36c506086a0a62980c056`](https://github.com/konst1970/dnipro4/commit/f634f73d2880fb1f57b36c506086a0a62980c056)). The extraction and subsequent
changes were requested by the project owner in this workspace.

EquiReduce adds its own application-independent input contract, domain tracking,
certificate checks, proof auditing, and portable artifact format. It has no
runtime import of Dnipro. Third-party dependencies are installed separately;
their source and compiled caches are not part of this Python distribution.

EquiReduce as distributed in this repository is licensed under the MIT License
(see `LICENSE`), selected by the project owner. This applies to the EquiReduce
code and documentation distributed here; separately installed dependencies
retain their own licenses. The development version is not a declaration that
a stable package release has been published.
