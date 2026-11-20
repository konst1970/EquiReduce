"""Exact affine trajectory charts, including M'(t) and c'(t)."""

from dataclasses import dataclass, replace

import sympy as sp

from equireduce import _core
from equireduce.conditions import (
    assumption_consistency,
    domain_conditions,
    normalize_conditions,
)
from equireduce.errors import CertificateError, InvalidSystemError
from equireduce.implicit import ImplicitDAESystem
from equireduce.implicit_reduction import (
    ImplicitReductionCertificate,
    reduce_implicit_dae,
    verify_implicit_certificate,
)
from equireduce.system import System


@dataclass(frozen=True)
class TimeAffineTransform:
    source: ImplicitDAESystem
    variables: tuple
    matrix: sp.ImmutableMatrix
    offset: sp.ImmutableMatrix
    determinant: sp.Expr
    inverse_matrix: sp.ImmutableMatrix
    forward_map: tuple
    inverse_map: tuple
    rate_map: tuple
    inverse_rate_map: tuple
    conditions: tuple

    @classmethod
    def create(cls, source, *, variables, matrix, offset=None):
        variables = tuple(variables)
        n = len(source.unknowns)
        if (
            len(variables) != n
            or len(set(variables)) != n
            or set(variables) & set((*source.unknowns, *source.inputs))
        ):
            raise InvalidSystemError(
                "time coordinates must be fresh distinct real functions"
            )
        ImplicitDAESystem.create(
            time=source.time,
            unknowns=variables,
            differential=variables,
            algebraic=(),
            residuals=(),
            interval=source.interval,
            parameters=source.parameters,
        )
        if any(
            any(
                getattr(v, "is_" + flag) is True
                for flag in (
                    "positive",
                    "negative",
                    "nonnegative",
                    "nonpositive",
                    "nonzero",
                    "zero",
                )
            )
            for v in variables
        ):
            raise InvalidSystemError(
                "new time coordinates must have an unrestricted real domain"
            )
        try:
            if not isinstance(matrix, sp.MatrixBase):
                matrix = tuple(tuple(row) for row in matrix)
                if any(
                    not isinstance(v, sp.Expr) and type(v) is not int
                    for row in matrix
                    for v in row
                ):
                    raise InvalidSystemError("matrix entries must be exact expressions")
            value = sp.ImmutableMatrix(matrix)
            raw_offset = (
                tuple(0 for _ in variables) if offset is None else tuple(offset)
            )
            if any(
                not isinstance(v, sp.Expr) and type(v) is not int for v in raw_offset
            ):
                raise InvalidSystemError("offset entries must be exact expressions")
            shift = sp.ImmutableMatrix(n, 1, raw_offset)
            if value.shape != (n, n):
                raise InvalidSystemError(
                    "time chart matrix must match the source dimension"
                )
            checked = System.algebraic(
                (*value, *shift), (), parameters=(source.time, *source.parameters)
            )
            if any(
                v.is_rational_function(source.time, *source.parameters) is not True
                for v in (*value, *shift)
            ):
                raise InvalidSystemError(
                    "time charts currently require rational time/parameter coefficients"
                )
            determinant = sp.factor(value.det(method="berkowitz"))
            if _core.symbolic_zero_status(determinant) is _core.SymbolicZeroStatus.ZERO:
                raise InvalidSystemError("time chart is singular")
            inverse = sp.ImmutableMatrix(value.inv(method="DM"))
        except InvalidSystemError:
            raise
        except (TypeError, ValueError, ArithmeticError) as exc:
            raise InvalidSystemError(f"invalid time chart: {exc}") from exc
        forward = value * sp.ImmutableMatrix(n, 1, variables) + shift
        backward = inverse * (sp.ImmutableMatrix(n, 1, source.unknowns) - shift)
        forward = tuple(sp.expand(v) for v in forward)
        backward = tuple(sp.cancel(v) for v in backward)
        rates = tuple(sp.diff(v, source.time) for v in forward)
        inverse_rates = tuple(sp.diff(v, source.time) for v in backward)
        guards = normalize_conditions(
            (
                *checked.conditions,
                *domain_conditions((*inverse, *backward, *rates, *inverse_rates)),
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
            tuple(zip(source.unknowns, forward, strict=True)),
            tuple(zip(variables, backward, strict=True)),
            tuple(
                zip(
                    (sp.diff(v, source.time) for v in source.unknowns),
                    rates,
                    strict=True,
                )
            ),
            tuple(
                zip(
                    (sp.diff(v, source.time) for v in variables),
                    inverse_rates,
                    strict=True,
                )
            ),
            guards,
        )


def verify_time_transform(source, transform):
    failed = _core.CertificateStatus.FAILED
    if not isinstance(transform, TimeAffineTransform) or transform.source != source:
        return _core.CertificateVerification(failed, ("time chart source mismatch",))
    try:
        expected = TimeAffineTransform.create(
            source,
            variables=transform.variables,
            matrix=transform.matrix,
            offset=transform.offset,
        )
        if expected != transform:
            return _core.CertificateVerification(
                failed, ("time chart inverse, rate map or domain mismatch",)
            )
        if any(
            _core.symbolic_zero_status(v) is not _core.SymbolicZeroStatus.ZERO
            for v in (
                *(
                    (transform.matrix * transform.inverse_matrix)
                    - sp.eye(len(transform.variables))
                ),
                *(
                    (transform.inverse_matrix * transform.matrix)
                    - sp.eye(len(transform.variables))
                ),
            )
        ):
            return _core.CertificateVerification(
                failed, ("time chart inverse identity failed",)
            )
    except (InvalidSystemError, ValueError, TypeError, AttributeError) as exc:
        return _core.CertificateVerification(failed, (str(exc),))
    return _core.CertificateVerification(_core.CertificateStatus.VERIFIED)


@dataclass(frozen=True)
class ImplicitCoordinateCertificate:
    source: ImplicitDAESystem
    transform: TimeAffineTransform
    inner: ImplicitReductionCertificate


def augmented_time_source(source, transform, differential, algebraic):
    return ImplicitDAESystem.create(
        time=source.time,
        unknowns=(*source.unknowns, *transform.variables),
        differential=tuple(differential),
        algebraic=(*source.unknowns, *algebraic),
        residuals=(
            *source.residuals,
            *(v - value for v, value in transform.forward_map),
        ),
        parameters=source.parameters,
        inputs=source.inputs,
        interval=source.interval,
        conditions=(*source.conditions, *transform.conditions),
        residual_names=(
            *source.residual_names,
            *(f"time_coordinate[{i}]" for i in range(len(transform.variables))),
        ),
        smooth_functions=source.smooth_functions,
        branch_choices=source.branch_choices,
    )


def verify_implicit_coordinate_certificate(source, certificate):
    failed = _core.CertificateStatus.FAILED
    if (
        not isinstance(certificate, ImplicitCoordinateCertificate)
        or certificate.source != source
    ):
        return _core.CertificateVerification(
            failed, ("coordinate DAE source mismatch",)
        )
    check = verify_time_transform(source, certificate.transform)
    if check.status.value != "verified":
        return check
    try:
        inner = certificate.inner
        new_alg = tuple(
            v for v in inner.source.algebraic if v in certificate.transform.variables
        )
        expected = augmented_time_source(
            source, certificate.transform, inner.source.differential, new_alg
        )
        if expected != inner.source:
            return _core.CertificateVerification(
                failed, ("augmented time-chart source mismatch",)
            )
        return verify_implicit_certificate(expected, inner)
    except (ValueError, TypeError, AttributeError) as exc:
        return _core.CertificateVerification(failed, (str(exc),))


def reduce_implicit_in_coordinates(
    source,
    transform,
    *,
    differential,
    algebraic,
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
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    check = verify_time_transform(source, transform)
    if check.status.value != "verified":
        raise CertificateError("; ".join(check.failures))
    augmented = augmented_time_source(
        source, transform, tuple(differential), tuple(algebraic)
    )
    from equireduce.dae import _exact_expression
    from equireduce.implicit_initial import resolve_initial_parameters

    if initial_time is not None:
        initial_time = _exact_expression(initial_time)
    parameters = resolve_initial_parameters(dict(parameter_values or {}))
    values = (
        None
        if initial_values is None
        else {k: _exact_expression(v) for k, v in initial_values.items()}
    )
    rates = (
        None
        if initial_rates is None
        else {k: _exact_expression(v) for k, v in initial_rates.items()}
    )
    if values is not None and initial_time is None:
        raise InvalidSystemError("initial time and values must be supplied together")
    if values is not None and set(source.unknowns) <= set(values):
        substitutions = {
            source.time: initial_time.xreplace(parameters),
            **parameters,
            **values,
        }
        for v, value in transform.inverse_map:
            values.setdefault(v, sp.cancel(value.xreplace(substitutions)))
        if rates is not None and all(
            sp.diff(v, source.time) in rates for v in source.unknowns
        ):
            substitutions.update(rates)
            for v, value in transform.inverse_rate_map:
                rates.setdefault(v, sp.cancel(value.xreplace(substitutions)))
    inner = reduce_implicit_dae(
        augmented,
        max_minors=max_minors,
        initial_time=initial_time,
        initial_values=values,
        initial_rates=rates,
        parameter_values=parameter_values,
        initial_input_values=initial_input_values,
        initial_input_rates=initial_input_rates,
    )
    certificate = ImplicitCoordinateCertificate(source, transform, inner.certificate)
    result = _wrap_implicit_coordinate(certificate, inner)
    if proof != "none":
        from equireduce.lean import attach_proof

        result = attach_proof(result, proof=proof, config=lean)
    return result


def _wrap_implicit_coordinate(certificate, inner):
    source = certificate.source
    transform = certificate.transform
    check = verify_implicit_coordinate_certificate(source, certificate)
    if check.status.value != "verified":
        raise CertificateError("; ".join(check.failures))
    reconstruction = {v: inner.reconstruction[v] for v in source.unknowns}
    derivatives = {
        sp.diff(v, source.time): inner.reconstruction_derivatives[
            sp.diff(v, source.time)
        ]
        for v in source.unknowns
    }
    inherited = normalize_conditions(
        v.xreplace(derivatives).xreplace(reconstruction) for v in source.conditions
    )
    additional = tuple(v for v in inner.conditions if v not in inherited)
    result = replace(
        inner,
        source=source,
        certificate=certificate,
        reconstruction=reconstruction,
        reconstruction_derivatives=derivatives,
        coordinate_map=transform,
        symbolic_check=check,
        additional_conditions=additional,
        coverage="conditional" if additional else "complete",
        assumption_consistency=assumption_consistency(inner.conditions),
    )
    return result
