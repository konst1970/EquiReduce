"""Experimental semi-explicit index-one DAE reduction on open intervals.

Differential states are differentiable trajectories. Reconstruction is restricted
to rational expressions in time, differential states and constant real parameters. This
restriction makes the regularity and chain-rule obligations checkable by Lean.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

import sympy as sp

from equireduce import _core
from equireduce.api import reduce_system, verify_certificate
from equireduce.conditions import (
    domain_conditions,
    intrinsic_conditions,
    normalize_conditions,
    validate_condition,
)
from equireduce.errors import (
    CertificateError,
    InvalidSystemError,
    UnsupportedDomainError,
)
from equireduce.result import Certificate, FormalCheck
from equireduce.system import System


def _exact_expression(value):
    if type(value) is int:
        return sp.Integer(value)
    if not isinstance(value, sp.Expr) or value.has(
        sp.Float, sp.Derivative, sp.zoo, sp.nan, sp.oo, -sp.oo
    ):
        raise InvalidSystemError(
            "exact finite SymPy expressions required; strings are not parsed"
        )
    return value


@dataclass(frozen=True)
class DAESystem:
    time: sp.Symbol
    differential: tuple
    algebraic: tuple
    rhs: tuple
    constraints: tuple
    interval: tuple
    parameters: tuple = ()
    conditions: tuple = ()

    def __post_init__(self):
        for name in (
            "differential",
            "algebraic",
            "rhs",
            "constraints",
            "interval",
            "parameters",
            "conditions",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        for name in ("rhs", "constraints"):
            object.__setattr__(
                self,
                name,
                tuple(
                    sp.Integer(v) if type(v) is int else v for v in getattr(self, name)
                ),
            )
        if any(not validate_condition(v) for v in self.conditions):
            raise InvalidSystemError("conditions must be Boolean SymPy predicates")
        object.__setattr__(self, "conditions", normalize_conditions(self.conditions))
        if not isinstance(self.time, sp.Symbol) or self.time.is_real is not True:
            raise InvalidSystemError("DAE time must be a real Symbol")
        states = self.differential + self.algebraic
        if (
            not self.differential
            or not self.algebraic
            or len(set(states)) != len(states)
        ):
            raise InvalidSystemError(
                "DAE states must be distinct, with differential states"
            )
        if any(
            not isinstance(v, sp.core.function.AppliedUndef)
            or v.args != (self.time,)
            or v.is_real is not True
            or any(
                getattr(v, "is_" + flag) is True
                for flag in (
                    "positive",
                    "negative",
                    "nonnegative",
                    "nonpositive",
                    "integer",
                    "rational",
                    "zero",
                    "nonzero",
                )
            )
            for v in states
        ):
            raise InvalidSystemError(
                "declare unrestricted real state functions of time"
            )
        intrinsic_conditions(states, ())
        if len(self.rhs) != len(self.differential) or len(self.constraints) != len(
            self.algebraic
        ):
            raise InvalidSystemError(
                "semi-explicit DAE requires a square algebraic block"
            )
        if self.time in self.parameters:
            raise InvalidSystemError("time cannot be a constant parameter")
        if any(
            not isinstance(e, sp.Expr) or e.has(sp.Derivative)
            for e in (*self.rhs, *self.constraints)
        ):
            raise UnsupportedDomainError(
                "semi-explicit rhs and constraints cannot contain derivatives"
            )
        if len(self.interval) != 2:
            raise InvalidSystemError("an open interval needs two endpoints")
        endpoints = tuple(_exact_expression(v) for v in self.interval)
        System.algebraic(endpoints, (), parameters=self.parameters)
        if (endpoints[0] < endpoints[1]) is sp.false:
            raise InvalidSystemError("open interval must be nonempty")
        object.__setattr__(self, "interval", endpoints)
        # Validate all expressions and capture domains before substitution.
        slots = self.slot_map
        checked = System.algebraic(
            tuple(e.xreplace(slots) for e in (*self.rhs, *self.constraints)),
            tuple(slots.values()),
            parameters=(self.time, *self.parameters),
            conditions=tuple(
                e.xreplace(slots)
                for e in (
                    *self.conditions,
                    *domain_conditions((*self.rhs, *self.constraints)),
                )
            ),
        )
        reverse = {v: k for k, v in slots.items()}
        object.__setattr__(
            self, "conditions", tuple(e.xreplace(reverse) for e in checked.conditions)
        )

    @property
    def interval_condition(self):
        return sp.Lt(*self.interval)

    @property
    def slot_map(self):
        occupied = {str(v) for v in (self.time, *self.parameters)}
        mapping = {}
        for index, state in enumerate(self.differential + self.algebraic):
            name = f"dae_state_{index}"
            while name in occupied:
                name += "_"
            occupied.add(name)
            mapping[state] = sp.Symbol(name, real=True)
        return mapping

    @classmethod
    def semi_explicit(
        cls,
        *,
        time,
        differential,
        algebraic,
        rhs,
        constraints,
        interval,
        parameters=(),
        conditions=(),
    ):
        """Declare ``x'=rhs(t,x,y,p), constraints(t,x,y,p)=0`` on ``(a,b)``."""
        return cls(
            time,
            differential,
            algebraic,
            rhs,
            constraints,
            interval,
            parameters,
            conditions,
        )


@dataclass(frozen=True)
class InitialCheck:
    status: str = "not_provided"
    time: sp.Expr | None = None
    values: tuple = ()
    obligations: tuple = ()


@dataclass(frozen=True)
class DAECertificate:
    source: DAESystem
    algebraic: Certificate
    reconstruction: tuple
    reduced_rhs: tuple
    conditions: tuple
    reconstruction_derivatives: tuple


@dataclass(frozen=True)
class RateSubstitution:
    """Residual substitution valid on the certified reconstruction graph."""

    source_residuals: tuple
    residuals: tuple
    conditions: tuple
    certificate: DAECertificate


@dataclass(frozen=True)
class DAEReductionResult:
    source: DAESystem
    reduced_rhs: tuple
    reduced_residuals: tuple
    reconstruction: Mapping
    reconstruction_derivatives: Mapping
    conditions: tuple
    additional_conditions: tuple
    coverage: str
    certificate: DAECertificate
    symbolic_check: _core.CertificateVerification
    initial_check: InitialCheck = field(default_factory=InitialCheck)
    formal_check: FormalCheck = field(default_factory=FormalCheck)
    domain_scope: str = "throughout_open_interval"

    def __post_init__(self):
        for name in ("reconstruction", "reconstruction_derivatives"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    def substitute_reconstructed_rates(self, residuals):
        """Substitute certified first rates on the reconstruction graph.

        The resulting residuals retain differential-state rates. This operation
        does not solve the new differential equations or lower their index.
        """
        residuals = tuple(residuals)
        replaced, conditions = _rate_substitution(self.certificate, residuals)
        return RateSubstitution(residuals, replaced, conditions, self.certificate)


def _rate_substitution(certificate, residuals):
    source = certificate.source
    result = []
    allowed = {sp.diff(v, source.time) for v in source.differential + source.algebraic}
    jets = {
        rate: sp.Dummy(f"rate_{i}", real=True)
        for i, rate in enumerate(sorted(allowed, key=sp.srepr))
    }
    for expression in residuals:
        if not isinstance(expression, sp.Expr):
            raise InvalidSystemError("rate substitution requires SymPy expressions")
        if expression.atoms(sp.Derivative) - allowed:
            raise UnsupportedDomainError(
                "only declared first-order rates may be substituted"
            )
        replaced = expression.xreplace(
            dict(certificate.reconstruction_derivatives)
        ).xreplace(dict(certificate.reconstruction))
        result.append(replaced)
    mapping = {**source.slot_map, **jets}
    checked = System.algebraic(
        tuple(e.xreplace(mapping) for e in residuals),
        tuple(mapping.values()),
        parameters=(source.time, *source.parameters),
        conditions=tuple(e.xreplace(mapping) for e in domain_conditions(residuals)),
    )
    reverse = {value: key for key, value in mapping.items()}
    guards = tuple(
        e.xreplace(reverse)
        .xreplace(dict(certificate.reconstruction_derivatives))
        .xreplace(dict(certificate.reconstruction))
        for e in checked.conditions
    )
    conditions = normalize_conditions(
        (*certificate.conditions, *guards, *domain_conditions(result))
    )
    return tuple(result), conditions


def verify_rate_substitution(record):
    """Check the DAE certificate, source domains and the complete rate substitution."""
    failed = _core.CertificateStatus.FAILED
    if not isinstance(record, RateSubstitution):
        return _core.CertificateVerification(
            failed, ("invalid rate substitution record",)
        )
    check = verify_dae_certificate(record.certificate.source, record.certificate)
    if check.status.value != "verified":
        return check
    try:
        residuals, conditions = _rate_substitution(
            record.certificate, record.source_residuals
        )
    except InvalidSystemError as exc:
        return _core.CertificateVerification(failed, (str(exc),))
    if residuals != record.residuals or conditions != record.conditions:
        return _core.CertificateVerification(
            failed, ("rate substitution/domain mismatch",)
        )
    return check


def _algebraic_source(source):
    slots = source.slot_map
    return System.algebraic(
        tuple(e.xreplace(slots) for e in source.constraints),
        tuple(slots[v] for v in source.algebraic),
        parameters=(
            source.time,
            *(slots[v] for v in source.differential),
            *source.parameters,
        ),
        conditions=tuple(e.xreplace(slots) for e in source.conditions),
    )


def _rational_reconstruction(expression, source):
    replaced = expression.xreplace(source.slot_map)
    variables = (source.time, *source.slot_map.values(), *source.parameters)
    # No opaque functions, radicals, Abs, Piecewise or unproved smoothness.
    return replaced.is_rational_function(*variables) is True


def _derived_fields(source, core):
    reverse = {v: k for k, v in source.slot_map.items()}
    reconstruction = tuple(
        (reverse[k], value.xreplace(reverse)) for k, value in core.reconstruction
    )
    mapping = dict(reconstruction)
    rhs = tuple(sp.cancel(e.xreplace(mapping)) for e in source.rhs)
    derivatives = tuple(
        (sp.diff(k, source.time), sp.diff(v, source.time)) for k, v in reconstruction
    )
    conditions = tuple(e.xreplace(reverse) for e in core.conditions)
    return reconstruction, rhs, conditions, derivatives


def verify_dae_certificate(source, certificate):
    """Replay elimination and independently recompute time-dependent data."""
    failed = _core.CertificateStatus.FAILED
    if not isinstance(certificate, DAECertificate) or source != certificate.source:
        return _core.CertificateVerification(failed, ("DAE source mismatch",))
    expected = _algebraic_source(source)
    if certificate.algebraic.source != expected:
        return _core.CertificateVerification(failed, ("algebraic DAE block mismatch",))
    check = verify_certificate(expected, certificate.algebraic)
    if check.status.value != "verified":
        return check
    core = certificate.algebraic.reduction
    if core.reduced_unknowns or core.reduced_residuals:
        return _core.CertificateVerification(
            failed, ("DAE algebraic block was not fully eliminated",)
        )
    decomposition = _core.decompose_affine_system(expected.residuals, expected.unknowns)
    if decomposition.status is not _core.AffineStatus.AFFINE:
        return _core.CertificateVerification(failed, ("DAE block is not affine",))
    derived = _derived_fields(source, core)
    actual = (
        certificate.reconstruction,
        certificate.reduced_rhs,
        certificate.conditions,
        certificate.reconstruction_derivatives,
    )
    if actual != derived:
        return _core.CertificateVerification(
            failed, ("DAE reconstruction/rate/domain mismatch",)
        )
    if any(
        not _rational_reconstruction(value, source)
        for _, value in certificate.reconstruction
    ):
        return _core.CertificateVerification(
            failed, ("reconstruction regularity is unsupported",)
        )
    return check


def _initial_check(source, certificate, time, values):
    if time is None and values is None:
        return InitialCheck()
    if time is None or values is None:
        raise InvalidSystemError("initial time and values must be supplied together")
    values = dict(values)
    states = source.differential + source.algebraic
    if set(values) != set(states):
        raise InvalidSystemError("initial values must cover all declared states")
    time = _exact_expression(time)
    values = {k: _exact_expression(v) for k, v in values.items()}
    for value in (time, *values.values()):
        if (
            not isinstance(value, sp.Expr)
            or value.has(sp.Float, sp.Derivative, sp.zoo, sp.nan)
            or value.is_real is False
        ):
            raise InvalidSystemError("initial values must be exact real expressions")
        if value.has(*states, source.time):
            raise InvalidSystemError("initial values cannot depend on time or states")
    substitutions = {source.time: time, **values}
    obligations = [time > source.interval[0], time < source.interval[1]]
    if any(sp.simplify(e) is sp.false for e in obligations):
        raise InvalidSystemError("initial time is outside the open interval")
    obligations += [e.xreplace(substitutions) for e in certificate.conditions]
    obligations += [
        sp.Eq(values[k], value.xreplace(substitutions))
        for k, value in certificate.reconstruction
    ]
    obligations += [
        sp.Eq(value.xreplace(substitutions), 0) for value in source.constraints
    ]
    obligations = [sp.simplify(e) for e in obligations]
    if any(e is sp.false for e in obligations):
        raise InvalidSystemError("incompatible initial values or domain conditions")
    pending = tuple(e for e in obligations if e is not sp.true)
    return InitialCheck(
        "conditional" if pending else "verified", time, tuple(values.items()), pending
    )


def reduce_dae(
    source, *, initial_time=None, initial_values=None, proof="none", lean=None
):
    """Eliminate the full affine algebraic block with interval-wide obligations."""
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    if not isinstance(source, DAESystem):
        raise InvalidSystemError("reduce_dae requires a DAESystem")
    algebraic = _algebraic_source(source)
    decomposition = _core.decompose_affine_system(
        algebraic.residuals, algebraic.unknowns
    )
    if decomposition.status is not _core.AffineStatus.AFFINE:
        raise UnsupportedDomainError("DAE algebraic block must be exactly affine")
    result = reduce_system(algebraic)
    assert isinstance(result.certificate, Certificate)
    if result.remaining_unknowns or result.reduced_system.residuals:
        raise UnsupportedDomainError(
            "DAE algebraic block must be invertible on an explicit domain"
        )
    fields = _derived_fields(source, result.certificate.reduction)
    if any(not _rational_reconstruction(value, source) for _, value in fields[0]):
        raise UnsupportedDomainError(
            "DAE classical reconstruction currently requires rational expressions"
        )
    certificate = DAECertificate(source, result.certificate, *fields)
    check = verify_dae_certificate(source, certificate)
    if check.status.value != "verified":
        raise CertificateError("; ".join(check.failures))
    public = _from_dae_certificate(
        certificate, initial_time=initial_time, initial_values=initial_values
    )
    if proof != "none":
        from equireduce.lean import attach_proof

        public = attach_proof(public, proof=proof, config=lean)
    return public


def _from_dae_certificate(certificate, *, initial_time=None, initial_values=None):
    source = certificate.source
    check = verify_dae_certificate(source, certificate)
    if check.status.value != "verified":
        raise CertificateError("; ".join(check.failures))
    additional = tuple(
        e
        for e in certificate.conditions
        if e
        not in normalize_conditions(
            condition.xreplace(dict(certificate.reconstruction))
            for condition in source.conditions
        )
    )
    return DAEReductionResult(
        source,
        certificate.reduced_rhs,
        tuple(
            sp.diff(v, source.time) - f
            for v, f in zip(source.differential, certificate.reduced_rhs, strict=True)
        ),
        dict(certificate.reconstruction),
        dict(certificate.reconstruction_derivatives),
        certificate.conditions,
        additional,
        "conditional" if additional else "complete",
        certificate,
        check,
        _initial_check(source, certificate, initial_time, initial_values),
    )
