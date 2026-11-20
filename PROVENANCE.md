# Code provenance

The affine reduction primitives in `src/equireduce/_core.py` and the initial
exporter in `_lean_export.py` were adapted from the Dnipro prototype
(`dnipro/analysis/reduction.py` and `lean_reduction.py`, repository commit
`f634f73d2880fb1f57b36c506086a0a62980c056`). The extraction and subsequent
changes were requested by the project owner in this workspace.

EquiReduce adds its own application-independent input contract, domain tracking,
certificate checks, proof auditing, and portable artifact format. It has no
runtime import of Dnipro. Third-party dependencies are installed separately;
their source and compiled caches are not part of this Python distribution.

A distribution license and public release metadata have not yet been chosen.
The development version is not a declaration that the package is ready for
publication or that upstream material has been relicensed.
