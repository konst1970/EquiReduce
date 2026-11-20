"""Immutable public result types and proof-mode configuration."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import TYPE_CHECKING, Any

import sympy as sp

if TYPE_CHECKING:
    from equireduce._core import CertificateVerification
    from equireduce._core import ReductionResult as CoreResult
    from equireduce.coordinates import AffineTransform
    from equireduce.system import System


class ProofStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    GENERATED = "generated"
    VERIFIED = "verified"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class FormalCheck:
    status: ProofStatus = ProofStatus.NOT_REQUESTED
    source: str | None = None
    output: str = ""
    returncode: int | None = None
    axioms: tuple = ()
    toolchain_version: str | None = None
    mathlib_revision: str | None = None
    source_sha256: str | None = None
    origin: str = "not_run"
    command: tuple = ()
    seconds: float | None = None
    checked_at_utc: str | None = None


@dataclass(frozen=True)
class LeanConfig:
    project_dir: str
    command: tuple = ("lake", "env", "lean")
    timeout_seconds: float = 120

    def __post_init__(self):
        if (
            isinstance(self.command, str)
            or not self.command
            or not all(isinstance(v, str) for v in self.command)
        ):
            raise ValueError("command must contain executable arguments")
        if not 0 < self.timeout_seconds < float("inf"):
            raise ValueError("timeout_seconds must be positive and finite")
        object.__setattr__(self, "command", tuple(self.command))


@dataclass(frozen=True)
class ReductionOptions:
    max_candidates: int = 32
    coordinate_search: bool = False
    float_policy: str = "reject"
    allow_blocks: bool = True
    coefficient_bound: int = 2

    def __post_init__(self):
        if type(self.max_candidates) is not int or self.max_candidates < 1:
            raise ValueError("max_candidates must be a positive integer")
        if self.float_policy not in ("reject", "exact_decimal"):
            raise ValueError("unknown float_policy")
        if type(self.coefficient_bound) is not int or self.coefficient_bound < 1:
            raise ValueError("coefficient_bound must be a positive integer")


@dataclass(frozen=True)
class Certificate:
    source: System
    reduction: CoreResult


@dataclass(frozen=True)
class CoordinateCertificate:
    source: System
    transform: AffineTransform
    inner: Certificate


@dataclass(frozen=True)
class ReductionResult:
    source: System
    reduced_system: System
    remaining_unknowns: tuple
    reconstruction: Mapping[sp.Symbol, sp.Expr]
    conditions: tuple
    additional_conditions: tuple
    coverage: str
    assumption_consistency: str
    certificate: Certificate | CoordinateCertificate
    symbolic_check: CertificateVerification
    formal_check: FormalCheck = field(default_factory=FormalCheck)
    coordinate_map: Any = None
    metrics: Any = None
    search: Any = None

    def __post_init__(self):
        object.__setattr__(
            self, "reconstruction", MappingProxyType(dict(self.reconstruction))
        )
