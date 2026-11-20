"""Exact affine coordinate maps and composed algebraic certificates."""

from __future__ import annotations

from dataclasses import dataclass, replace

import sympy as sp

from equireduce import _core
from equireduce.api import _canonical, _from_core, reduce_system, verify_certificate
from equireduce.conditions import assumption_consistency, domain_conditions
from equireduce.errors import CertificateError, InvalidSystemError
from equireduce.metrics import measure
from equireduce.result import Certificate, CoordinateCertificate, ReductionResult
from equireduce.system import System


@dataclass(frozen=True)
class AffineTransform:
    """An exact bijective chart ``X = matrix*U + offset`` on an explicit domain."""

    source: System
    variables: tuple
    matrix: sp.ImmutableMatrix
    offset: sp.ImmutableMatrix
    determinant: sp.Expr
    inverse_matrix: sp.ImmutableMatrix
    forward_map: tuple
    inverse_map: tuple
    conditions: tuple

    @classmethod
    def create(
        cls, source: System, *, variables, matrix, offset=None
    ) -> AffineTransform:
        variables = tuple(variables)
        size = len(source.unknowns)
        if (
            len(variables) != size
            or len(set(variables)) != size
            or set(variables) & set((*source.unknowns, *source.parameters))
            or any(
                not isinstance(v, sp.Symbol) or v.is_real is not True for v in variables
            )
        ):
            raise InvalidSystemError(
                "coordinate variables must be fresh distinct real Symbols"
            )
        if any(set(v._assumptions_orig) - {"real", "commutative"} for v in variables):
            raise InvalidSystemError(
                "new coordinates must have an unrestricted real domain"
            )
        try:
            if not isinstance(matrix, sp.MatrixBase):
                matrix = tuple(tuple(row) for row in matrix)
                if any(
                    isinstance(entry, (str, bool)) for row in matrix for entry in row
                ):
                    raise InvalidSystemError("matrix entries must be exact expressions")
            value = sp.ImmutableMatrix(matrix)
            raw_offset = (
                tuple(0 for _ in variables) if offset is None else tuple(offset)
            )
            if any(isinstance(entry, (str, bool)) for entry in raw_offset):
                raise InvalidSystemError("offset must contain exact expressions")
            shift = sp.ImmutableMatrix(size, 1, raw_offset)
            if value.shape != (size, size):
                raise InvalidSystemError(
                    "coordinate matrix must be square and match dimension"
                )
            checked = System.algebraic(
                (*value, *shift), (), parameters=source.parameters
            )
            determinant = sp.factor(value.det())
            if _core.symbolic_zero_status(determinant) is _core.SymbolicZeroStatus.ZERO:
                raise InvalidSystemError("coordinate matrix is singular")
            inverse = sp.ImmutableMatrix(value.inv())
        except InvalidSystemError:
            raise
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidSystemError(f"invalid affine transform: {exc}") from exc
        forward = value * sp.ImmutableMatrix(size, 1, variables) + shift
        backward = inverse * (sp.ImmutableMatrix(size, 1, source.unknowns) - shift)
        guards = _canonical(
            (
                *checked.conditions,
                *domain_conditions((*inverse, *forward, *backward)),
                sp.Ne(determinant, 0),
            )
        )
        return cls(
            source,
            variables,
            value,
            shift,
            determinant,
            inverse,
            tuple(zip(source.unknowns, map(sp.cancel, forward), strict=True)),
            tuple(zip(variables, map(sp.cancel, backward), strict=True)),
            guards,
        )


def verify_transform(source: System, transform: AffineTransform):
    """Reconstruct both maps independently from the matrix and compare the data."""
    failed = _core.CertificateStatus.FAILED
    if not isinstance(transform, AffineTransform):
        return _core.CertificateVerification(failed, ("invalid coordinate record",))
    if transform.source != source:
        return _core.CertificateVerification(failed, ("coordinate source mismatch",))
    try:
        expected = AffineTransform.create(
            source,
            variables=transform.variables,
            matrix=transform.matrix,
            offset=transform.offset,
        )
    except InvalidSystemError as exc:
        return _core.CertificateVerification(failed, (str(exc),))
    if expected != transform:
        return _core.CertificateVerification(
            failed, ("affine inverse/map/guard mismatch",)
        )
    for image in (
        *(
            transform.matrix * transform.inverse_matrix
            - sp.eye(len(transform.variables))
        ),
        *(
            transform.inverse_matrix * transform.matrix
            - sp.eye(len(transform.variables))
        ),
    ):
        if _core.symbolic_zero_status(image) is not _core.SymbolicZeroStatus.ZERO:
            return _core.CertificateVerification(
                failed, ("affine inverse identity failed",)
            )
    return _core.CertificateVerification(_core.CertificateStatus.VERIFIED)


def transformed_system(source: System, transform: AffineTransform) -> System:
    substitutions = dict(transform.forward_map)
    return System.algebraic(
        tuple(row.subs(substitutions, simultaneous=True) for row in source.residuals),
        transform.variables,
        parameters=source.parameters,
        conditions=(
            *(
                condition.subs(substitutions, simultaneous=True)
                for condition in source.conditions
            ),
            *transform.conditions,
        ),
        residual_names=source.residual_names,
    )


def verify_coordinate_certificate(source: System, certificate: CoordinateCertificate):
    failed = _core.CertificateStatus.FAILED
    if certificate.source != source:
        return _core.CertificateVerification(failed, ("composite source mismatch",))
    check = verify_transform(source, certificate.transform)
    if check.status is not _core.CertificateStatus.VERIFIED:
        return check
    expected = transformed_system(source, certificate.transform)
    if certificate.inner.source != expected:
        return _core.CertificateVerification(
            failed, ("transformed source/domain mismatch",)
        )
    return verify_certificate(expected, certificate.inner)


def _from_coordinate_certificate(certificate: CoordinateCertificate) -> ReductionResult:
    check = verify_coordinate_certificate(certificate.source, certificate)
    if check.status is not _core.CertificateStatus.VERIFIED:
        raise CertificateError("; ".join(check.failures))
    inner = _from_core(certificate.inner.source, certificate.inner.reduction)
    reconstruction = {
        variable: sp.cancel(value.subs(dict(inner.reconstruction), simultaneous=True))
        for variable, value in certificate.transform.forward_map
    }
    inherited = _canonical(
        condition.subs(reconstruction, simultaneous=True)
        for condition in certificate.source.conditions
    )
    additional = tuple(value for value in inner.conditions if value not in inherited)
    return ReductionResult(
        source=certificate.source,
        reduced_system=inner.reduced_system,
        remaining_unknowns=inner.remaining_unknowns,
        reconstruction=reconstruction,
        conditions=inner.conditions,
        additional_conditions=additional,
        coverage="conditional" if additional else "complete",
        assumption_consistency=assumption_consistency(inner.conditions),
        certificate=certificate,
        symbolic_check=check,
        coordinate_map=certificate.transform,
        metrics=measure(certificate.source, inner.reduced_system, reconstruction),
    )


def reduce_in_coordinates(
    source: System,
    transform: AffineTransform,
    *,
    candidates=None,
    options=None,
    proof="none",
    lean=None,
) -> ReductionResult:
    """Reduce in a certified affine chart and reconstruct every original variable."""
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    check = verify_transform(source, transform)
    if check.status is not _core.CertificateStatus.VERIFIED:
        raise CertificateError("; ".join(check.failures))
    inner = reduce_system(
        transformed_system(source, transform), candidates=candidates, options=options
    )
    if not isinstance(inner.certificate, Certificate):
        raise CertificateError("nested coordinate search requires a separate chart")
    certificate = CoordinateCertificate(source, transform, inner.certificate)
    result = _from_coordinate_certificate(certificate)
    if proof != "none":
        from equireduce.lean import attach_proof

        result = attach_proof(result, proof=proof, config=lean)
    return result


def augmented_certificate(certificate: CoordinateCertificate):
    """Build one replayable trace for the original equations plus chart constraints."""
    source, transform, inner = (
        certificate.source,
        certificate.transform,
        certificate.inner.reduction,
    )
    equations = tuple(variable - value for variable, value in transform.forward_map)
    chart_names = tuple(f"coordinate[{i}]" for i in range(len(equations)))
    augmented = System.algebraic(
        (*source.residuals, *equations),
        (*source.unknowns, *transform.variables),
        parameters=source.parameters,
        conditions=(*source.conditions, *transform.conditions),
        residual_names=(*source.residual_names, *chart_names),
    )
    accumulated: dict = {}
    steps: list[_core.ReductionStep | _core.ReductionBlockStep] = []
    for index, (variable, value) in enumerate(transform.forward_map):
        steps.append(
            _core.ReductionStep(
                equation_index=len(source.residuals) + index,
                equation_name=chart_names[index],
                variable=variable,
                coefficient=sp.S.One,
                remainder=-value,
                guard=sp.true,
                pivot_residual=equations[index],
                prior_substitutions=tuple(accumulated.items()),
            )
        )
        accumulated[variable] = value
    for step in inner.steps:
        prior = tuple(
            (v, accumulated[v]) for v in augmented.unknowns if v in accumulated
        )
        steps.append(replace(step, prior_substitutions=prior))
        substitutions = (
            {step.variable: step.reconstruction_expression}
            if isinstance(step, _core.ReductionStep)
            else dict(step.reconstruction)
        )
        accumulated = {
            variable: sp.cancel(value.subs(substitutions, simultaneous=True))
            for variable, value in accumulated.items()
        }
        accumulated.update(
            {variable: sp.cancel(value) for variable, value in substitutions.items()}
        )
    combined = _core.ReductionResult(
        source_domain="algebraic",
        source_unknowns=augmented.unknowns,
        source_residuals=augmented.residuals,
        source_residual_names=augmented.residual_names,
        reduced_unknowns=inner.reduced_unknowns,
        reduced_residuals=inner.reduced_residuals,
        reduced_residual_indices=inner.reduced_residual_indices,
        eliminated_unknowns=tuple(v for v in augmented.unknowns if v in accumulated),
        reconstruction=tuple(
            (v, accumulated[v]) for v in augmented.unknowns if v in accumulated
        ),
        conditions=inner.conditions,
        steps=tuple(steps),
    )
    from equireduce.result import Certificate

    return Certificate(augmented, combined)
