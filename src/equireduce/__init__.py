"""Exact symbolic equation reduction and independently checked certificates."""

from equireduce._version import __version__
from equireduce.api import reduce_system, verify_certificate
from equireduce.artifacts import export_artifact, load_artifact
from equireduce.coordinates import AffineTransform, reduce_in_coordinates
from equireduce.dae import (
    DAEReductionResult,
    DAESystem,
    RateSubstitution,
    reduce_dae,
    verify_dae_certificate,
    verify_rate_substitution,
)
from equireduce.dae_structure import (
    analyze_implicit_dae,
    analyze_symbolic_rank,
    verify_implicit_structure,
)
from equireduce.errors import (
    ArtifactError,
    CertificateError,
    EquiReduceError,
    InvalidSystemError,
    ProofVerificationError,
    UnsupportedDomainError,
    UnsupportedExpressionError,
)
from equireduce.implicit import ImplicitDAESystem
from equireduce.implicit_reduction import (
    ImplicitDAEReductionResult,
    reduce_implicit_dae,
    verify_implicit_certificate,
)
from equireduce.implicit_search import search_implicit_partitions
from equireduce.lean import generate_lean, verify_with_lean
from equireduce.result import LeanConfig, ReductionOptions, ReductionResult
from equireduce.search import benchmark_coordinates, search_coordinates
from equireduce.smooth import SmoothFunction
from equireduce.system import System
from equireduce.time_coordinates import (
    TimeAffineTransform,
    reduce_implicit_in_coordinates,
    verify_implicit_coordinate_certificate,
    verify_time_transform,
)

__all__ = [
    "SmoothFunction",
    "ImplicitDAESystem",
    "search_implicit_partitions",
    "TimeAffineTransform",
    "reduce_implicit_in_coordinates",
    "verify_time_transform",
    "verify_implicit_coordinate_certificate",
    "ImplicitDAEReductionResult",
    "reduce_implicit_dae",
    "verify_implicit_certificate",
    "analyze_implicit_dae",
    "analyze_symbolic_rank",
    "verify_implicit_structure",
    "DAESystem",
    "DAEReductionResult",
    "RateSubstitution",
    "reduce_dae",
    "verify_dae_certificate",
    "verify_rate_substitution",
    "search_coordinates",
    "benchmark_coordinates",
    "AffineTransform",
    "reduce_in_coordinates",
    "__version__",
    "ArtifactError",
    "CertificateError",
    "EquiReduceError",
    "InvalidSystemError",
    "LeanConfig",
    "ProofVerificationError",
    "ReductionOptions",
    "ReductionResult",
    "System",
    "UnsupportedDomainError",
    "UnsupportedExpressionError",
    "reduce_system",
    "verify_certificate",
    "generate_lean",
    "verify_with_lean",
    "export_artifact",
    "load_artifact",
]
