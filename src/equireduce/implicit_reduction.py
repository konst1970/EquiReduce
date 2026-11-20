"""Algebraic-block reduction that preserves an implicit first-order DAE."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TYPE_CHECKING

import sympy as sp

from equireduce import _core
from equireduce.api import reduce_system, verify_certificate
from equireduce.conditions import (
    assumption_consistency,
    domain_conditions,
    normalize_conditions,
)
from equireduce.dae_structure import (
    DerivativeNormalization,
    ImplicitDAEStructure,
    analyze_implicit_dae,
    normalize_implicit_dae,
)
from equireduce.errors import (
    CertificateError,
    InvalidSystemError,
    UnsupportedDomainError,
)
from equireduce.implicit import ImplicitDAESystem, substitute_condition
from equireduce.implicit_initial import ImplicitInitialCheck, check_implicit_initial
from equireduce.result import Certificate, FormalCheck
from equireduce.smooth import time_derivative
from equireduce.system import System

if TYPE_CHECKING:
    from equireduce.time_coordinates import ImplicitCoordinateCertificate


@dataclass(frozen=True)
class ImplicitReductionCertificate:
    source: ImplicitDAESystem
    normalization: DerivativeNormalization
    algebraic_row_indices: tuple
    algebraic: Certificate
    reconstruction: tuple
    reconstruction_derivatives: tuple
    reduced_residuals: tuple
    residual_source_indices: tuple
    conditions: tuple


@dataclass(frozen=True)
class ImplicitDAEReductionResult:
    source: ImplicitDAESystem
    reduced_system: ImplicitDAESystem
    remaining_unknowns: tuple
    reconstruction: Mapping
    reconstruction_derivatives: Mapping
    conditions: tuple
    additional_conditions: tuple
    coverage: str
    assumption_consistency: str
    residual_source_indices: tuple
    certificate: ImplicitReductionCertificate | ImplicitCoordinateCertificate
    symbolic_check: _core.CertificateVerification
    structure: ImplicitDAEStructure
    initial_check: ImplicitInitialCheck = field(default_factory=ImplicitInitialCheck)
    formal_check: FormalCheck = field(default_factory=FormalCheck)
    form: str = "implicit"
    index_status: str = "not_classified"
    domain_scope: str = "throughout_open_interval"
    search: object = None
    coordinate_map: object = None
    provenance: Mapping | None = None

    def __post_init__(self):
        from equireduce.provenance import freeze

        object.__setattr__(self, "provenance", freeze(self.provenance))
        for name in ("reconstruction", "reconstruction_derivatives"):
            object.__setattr__(self, name, MappingProxyType(dict(getattr(self, name))))

    @property
    def required_input_rates(self):
        """Actual prescribed input derivatives required by this result."""
        certificate = self.certificate
        if not isinstance(certificate, ImplicitReductionCertificate):
            certificate = certificate.inner
        expressions = (
            *self.reduced_system.residuals,
            *self.conditions,
            *self.reconstruction_derivatives.values(),
            *certificate.normalization.residuals,
            *certificate.normalization.conditions,
        )
        return tuple(
            rate
            for rate in (sp.Derivative(v, self.source.time) for v in self.source.inputs)
            if any(expression.has(rate) for expression in expressions)
        )


def _algebraic_problem(source, normalization):
    indices = tuple(
        i for i, v in enumerate(normalization.residuals) if not v.has(sp.Derivative)
    )
    mapping = {**source.slot_map, **source.rate_map}
    unknowns = tuple(mapping[v] for v in source.algebraic)
    parameters = (
        source.time,
        *source.parameters,
        *(v for v in mapping.values() if v not in unknowns),
    )
    problem = System.algebraic(
        tuple(normalization.residuals[i].xreplace(mapping) for i in indices),
        unknowns,
        parameters=parameters,
        conditions=tuple(
            substitute_condition(v, mapping) for v in normalization.conditions
        ),
        residual_names=tuple(source.residual_names[i] for i in indices),
    )
    return indices, problem


def _transport(condition, reconstruction, derivatives):
    return substitute_condition(
        substitute_condition(condition, derivatives), reconstruction
    )


def _derived_fields(source, normalization, algebraic):
    mapping = {**source.slot_map, **source.rate_map}
    reverse = {v: k for k, v in mapping.items()}
    core = algebraic.reduction
    if core.reduced_unknowns:
        raise UnsupportedDomainError(
            "requested algebraic block cannot be fully eliminated; "
            "check the partition, nonlinearity or higher index"
        )
    reconstruction = tuple(
        (reverse[k], value.xreplace(reverse)) for k, value in core.reconstruction
    )
    for _, value in reconstruction:
        if value.has(sp.Derivative):
            raise UnsupportedDomainError(
                "implicit algebraic reconstruction currently requires "
                "smooth expressions without rates"
            )
    derivatives = tuple(
        (sp.Derivative(v, source.time), time_derivative(value, source))
        for v, value in reconstruction
    )
    rec, rates = dict(reconstruction), dict(derivatives)
    allowed = {
        sp.Derivative(v, source.time) for v in (*source.differential, *source.inputs)
    }
    if any(value.atoms(sp.Derivative) - allowed for _, value in derivatives):
        raise UnsupportedDomainError(
            "reconstruction would introduce unsupported or higher derivatives"
        )
    images = tuple(v.xreplace(rates).xreplace(rec) for v in normalization.residuals)
    inherited = tuple(_transport(v, rec, rates) for v in normalization.conditions)
    inner = tuple(
        _transport(substitute_condition(v, reverse), rec, rates)
        for v in core.conditions
    )
    guards = normalize_conditions(
        (
            *inherited,
            *inner,
            *domain_conditions(
                (*images, *(v for _, v in reconstruction), *(v for _, v in derivatives))
            ),
        )
    )
    indices = tuple(
        i
        for i, v in enumerate(images)
        if _core.symbolic_zero_status(v) is not _core.SymbolicZeroStatus.ZERO
    )
    residuals = tuple(sp.cancel(images[i]) for i in indices)
    return reconstruction, derivatives, residuals, indices, guards


def verify_implicit_certificate(source, certificate):
    """Replay normalization, the algebraic trace, the chain rule and every row.

    This is exact symbolic verification. The complete interval trajectory
    theorem is generated and kernel-checked separately via ``proof="require"``.
    """
    failed = _core.CertificateStatus.FAILED
    if (
        not isinstance(source, ImplicitDAESystem)
        or not isinstance(certificate, ImplicitReductionCertificate)
        or source != certificate.source
    ):
        return _core.CertificateVerification(failed, ("implicit DAE source mismatch",))
    try:
        normalized = normalize_implicit_dae(source)
        if normalized != certificate.normalization:
            return _core.CertificateVerification(
                failed, ("derivative normalization mismatch",)
            )
        analysis = analyze_implicit_dae(source, max_minors=1)
        if analysis.status is not _core.AffineStatus.AFFINE:
            return _core.CertificateVerification(
                failed, ("source is not affine in its state rates",)
            )
        indices, problem = _algebraic_problem(source, normalized)
        if (
            indices != certificate.algebraic_row_indices
            or not isinstance(certificate.algebraic, Certificate)
            or certificate.algebraic.source != problem
        ):
            return _core.CertificateVerification(
                failed, ("algebraic source rows/domain mismatch",)
            )
        check = verify_certificate(problem, certificate.algebraic)
        if check.status is not _core.CertificateStatus.VERIFIED:
            return check
        expected = _derived_fields(source, normalized, certificate.algebraic)
        actual = (
            certificate.reconstruction,
            certificate.reconstruction_derivatives,
            certificate.reduced_residuals,
            certificate.residual_source_indices,
            certificate.conditions,
        )
        if actual != expected:
            return _core.CertificateVerification(
                failed,
                ("implicit residual, chain rule, source indices or domain mismatch",),
            )
    except (InvalidSystemError, ValueError, TypeError, AttributeError) as exc:
        return _core.CertificateVerification(failed, (str(exc),))
    return _core.CertificateVerification(_core.CertificateStatus.VERIFIED)


def reduce_implicit_dae(
    source,
    *,
    proof="none",
    lean=None,
    max_minors=64,
    initial_time=None,
    initial_values=None,
    initial_rates=None,
    parameter_values=None,
    initial_input_values=None,
    initial_input_rates=None,
):
    """Eliminate a manual algebraic block without inverting the mass matrix."""
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    if not isinstance(source, ImplicitDAESystem):
        raise InvalidSystemError("expected an ImplicitDAESystem")
    analysis = analyze_implicit_dae(source, max_minors=max_minors)
    if analysis.status is not _core.AffineStatus.AFFINE:
        raise UnsupportedDomainError(
            "implicit first-order reduction requires affinity in unknown-state rates"
        )
    indices, problem = _algebraic_problem(source, analysis.normalization)
    algebraic = reduce_system(problem)
    assert isinstance(algebraic.certificate, Certificate)
    derived = _derived_fields(source, analysis.normalization, algebraic.certificate)
    certificate = ImplicitReductionCertificate(
        source, analysis.normalization, indices, algebraic.certificate, *derived
    )
    result = _from_implicit_certificate(
        certificate,
        max_minors=max_minors,
        initial_time=initial_time,
        initial_values=initial_values,
        initial_rates=initial_rates,
        parameter_values=parameter_values,
        initial_input_values=initial_input_values,
        initial_input_rates=initial_input_rates,
    )
    if proof != "none":
        from equireduce.lean import attach_proof

        result = attach_proof(result, proof=proof, config=lean)
    return result


def _from_implicit_certificate(
    certificate,
    *,
    max_minors=64,
    initial_time=None,
    initial_values=None,
    initial_rates=None,
    parameter_values=None,
    initial_input_values=None,
    initial_input_rates=None,
):
    """Rebuild result fields from a checked trace without elimination/search."""
    source = certificate.source
    check = verify_implicit_certificate(source, certificate)
    if check.status is not _core.CertificateStatus.VERIFIED:
        raise CertificateError("; ".join((*check.failures, *check.unresolved)))
    reconstruction = dict(certificate.reconstruction)
    derivatives = dict(certificate.reconstruction_derivatives)
    inherited = normalize_conditions(
        _transport(v, reconstruction, derivatives) for v in source.conditions
    )
    additional = tuple(v for v in certificate.conditions if v not in inherited)
    remaining = tuple(v for v in source.unknowns if v not in reconstruction)
    reduced = ImplicitDAESystem.create(
        time=source.time,
        unknowns=remaining,
        differential=tuple(v for v in source.differential if v in remaining),
        algebraic=(),
        residuals=certificate.reduced_residuals,
        interval=source.interval,
        parameters=source.parameters,
        inputs=source.inputs,
        conditions=certificate.conditions,
        residual_names=tuple(
            source.residual_names[i] for i in certificate.residual_source_indices
        ),
        smooth_functions=source.smooth_functions,
    )
    result = ImplicitDAEReductionResult(
        source,
        reduced,
        remaining,
        reconstruction,
        derivatives,
        certificate.conditions,
        additional,
        "conditional" if additional else "complete",
        assumption_consistency(certificate.conditions),
        certificate.residual_source_indices,
        certificate,
        check,
        analyze_implicit_dae(reduced, max_minors=max_minors),
    )
    result = replace(
        result,
        initial_check=check_implicit_initial(
            result,
            initial_time=initial_time,
            initial_values=initial_values,
            initial_rates=initial_rates,
            parameter_values=parameter_values,
            initial_input_values=initial_input_values,
            initial_input_rates=initial_input_rates,
        ),
    )
    return result
