"""Exact derivative normalization, rate affinity and bounded minor certificates."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations

import sympy as sp

from equireduce import _core
from equireduce.conditions import (
    domain_conditions,
    normalize_conditions,
    validate_condition,
)
from equireduce.errors import InvalidSystemError, UnsupportedDomainError
from equireduce.implicit import ImplicitDAESystem, substitute_condition
from equireduce.smooth import branch_data, raw_replace, time_derivative


@dataclass(frozen=True)
class DerivativeNormalization:
    source: ImplicitDAESystem
    residuals: tuple
    conditions: tuple
    additional_conditions: tuple
    rewrites: tuple


def normalize_implicit_dae(source):
    if not isinstance(source, ImplicitDAESystem):
        raise InvalidSystemError("expected an ImplicitDAESystem")
    expressions = (*source.residuals, *source.conditions)
    branches, _ = branch_data(expressions, source.branch_choices)
    selected = tuple(raw_replace(v, branches) for v in expressions)
    active_derivatives = set().union(*(v.atoms(sp.Derivative) for v in selected))
    derivatives = set().union(*(v.atoms(sp.Derivative) for v in expressions))
    rewrites = {}
    for derivative in sorted(derivatives, key=sp.srepr):
        picked = raw_replace(derivative, branches)
        if picked not in active_derivatives:
            continue
        if derivative.expr in (*source.unknowns, *source.inputs):
            continue
        value = time_derivative(picked.expr, source)
        if value.atoms(sp.Derivative) - source.rate_map.keys():
            raise UnsupportedDomainError(
                "normalization produced an unsupported or higher derivative"
            )
        rewrites[derivative] = value
    rows = tuple(
        sp.cancel(raw_replace(v, {**branches, **rewrites})) for v in source.residuals
    )
    inherited = normalize_conditions(
        substitute_condition(v, {**branches, **rewrites}) for v in source.conditions
    )
    conditions = normalize_conditions(
        (*inherited, *domain_conditions((*rows, *inherited)))
    )
    return DerivativeNormalization(
        source,
        rows,
        conditions,
        tuple(v for v in conditions if v not in inherited),
        tuple(rewrites.items()),
    )


@dataclass(frozen=True)
class SymbolicRank:
    status: str
    rank: int | None
    lower_bound: int
    upper_bound: int
    conditions: tuple
    pivot_rows: tuple
    pivot_columns: tuple
    witness: sp.Expr | None
    minors_examined: int
    max_minors: int
    budget_exhausted: bool


def _structural_bound(matrix):
    edges = [
        [j for j in range(matrix.cols) if sp.cancel(matrix[i, j]) != 0]
        for i in range(matrix.rows)
    ]
    matching: dict[int, int] = {}

    def augment(row, visited):
        for column in edges[row]:
            if column in visited:
                continue
            visited.add(column)
            if column not in matching or augment(matching[column], visited):
                matching[column] = row
                return True
        return False

    for row in range(matrix.rows):
        augment(row, set())
    return len(matching)


def _known_nonzero(value, conditions):
    if value.is_zero is False:
        return True
    return all(
        v in conditions
        for v in normalize_conditions((sp.Ne(value, 0, evaluate=False),))
    )


def analyze_symbolic_rank(matrix, *, conditions=(), max_minors=64):
    """Prove a rank or return bounds; generic rank guards never become DAE guards.

    Unknown functions remain unresolved unless the domain supplies nonvanishing.
    The matching bound is only structural. No numeric sampling or numeric rank
    calculation is used, and the finite minor budget is reported explicitly.
    """
    if type(max_minors) is not int or max_minors < 1:
        raise ValueError("max_minors must be a positive integer")
    try:
        if not isinstance(matrix, sp.MatrixBase):
            matrix = tuple(tuple(row) for row in matrix)
            if any(
                not isinstance(v, sp.Expr) and type(v) is not int
                for row in matrix
                for v in row
            ):
                raise InvalidSystemError(
                    "rank matrix entries must be exact expressions"
                )
        matrix = sp.ImmutableMatrix(matrix)
    except (TypeError, ValueError) as exc:
        raise InvalidSystemError(f"invalid rank matrix: {exc}") from exc
    if any(v.has(sp.Float, sp.nan, sp.zoo, sp.oo, -sp.oo) for v in matrix):
        raise InvalidSystemError("rank analysis requires exact finite expressions")
    conditions = tuple(conditions)
    if any(not validate_condition(v) for v in conditions):
        raise InvalidSystemError("rank conditions must be predicates")
    conditions = normalize_conditions(conditions)
    upper = _structural_bound(matrix)
    lower = 0
    examined = 0
    conditional = None
    proven = None
    exhausted = False
    for size in range(upper, 0, -1):
        all_zero = True
        for rows in combinations(range(matrix.rows), size):
            for columns in combinations(range(matrix.cols), size):
                if examined >= max_minors:
                    exhausted = True
                    break
                determinant = sp.factor(
                    matrix.extract(rows, columns).det(method="berkowitz")
                )
                examined += 1
                identity_status = _core.symbolic_zero_status(determinant)
                if identity_status is _core.SymbolicZeroStatus.ZERO:
                    continue
                all_zero = False
                witness = (size, rows, columns, determinant)
                if _known_nonzero(determinant, conditions):
                    if size > lower:
                        lower, proven = size, witness
                    if lower == upper:
                        break
                elif (
                    identity_status is _core.SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
                    and conditional is None
                ):
                    conditional = witness
            if exhausted or lower == upper:
                break
        if exhausted or lower == upper:
            break
        if all_zero:
            upper = min(upper, size - 1)
        if lower >= size:
            break
    if lower == upper:
        selected = proven
        status, rank, guards = "exact", lower, ()
    elif conditional is not None and conditional[0] == upper:
        selected = conditional
        status, rank, guards = (
            "conditional",
            upper,
            normalize_conditions((sp.Ne(selected[3], 0, evaluate=False),)),
        )
    else:
        selected = proven
        status, rank, guards = "unknown", None, ()
    return SymbolicRank(
        status,
        rank,
        lower,
        upper,
        guards,
        selected[1] if selected else (),
        selected[2] if selected else (),
        selected[3] if selected else None,
        examined,
        max_minors,
        exhausted,
    )


@dataclass(frozen=True)
class ImplicitDAEStructure:
    normalization: DerivativeNormalization
    derivatives: tuple
    input_derivatives: tuple
    status: _core.AffineStatus
    mass_matrix: sp.ImmutableMatrix
    offset: sp.ImmutableMatrix
    rank: SymbolicRank | None
    reason: str | None = None


def analyze_implicit_dae(source, *, max_minors=64):
    """Check ``F = E*X' + h`` exactly without claiming an index or an ODE."""
    normalized = normalize_implicit_dae(source)
    mapping = {**source.slot_map, **source.rate_map}
    reverse = {v: k for k, v in mapping.items()}
    rates = tuple(sp.Derivative(v, source.time) for v in source.unknowns)
    rate_slots = tuple(mapping[v] for v in rates)
    residuals = sp.ImmutableMatrix(
        len(normalized.residuals),
        1,
        [v.xreplace(mapping) for v in normalized.residuals],
    )
    matrix = (
        residuals.jacobian(rate_slots) if rate_slots else sp.zeros(len(residuals), 0)
    ).applyfunc(sp.cancel)
    offset = (
        residuals - matrix * sp.ImmutableMatrix(len(rate_slots), 1, rate_slots)
    ).applyfunc(sp.cancel)
    status = _core.AffineStatus.AFFINE
    reason = None
    if any(v.has(*rate_slots) for v in (*matrix, *offset)) if rate_slots else False:
        checked = _core.decompose_affine_system(tuple(residuals), rate_slots)
        status = (
            checked.status
            if checked.status is not _core.AffineStatus.AFFINE
            else _core.AffineStatus.UNKNOWN
        )
        reason = (
            "rate independence is false or unresolved; "
            "mass coefficients or offset still contain rates"
        )
    elif any(
        _core.symbolic_zero_status(v) is not _core.SymbolicZeroStatus.ZERO
        for v in residuals
        - matrix * sp.ImmutableMatrix(len(rate_slots), 1, rate_slots)
        - offset
    ):
        status = _core.AffineStatus.UNKNOWN
        reason = "rate decomposition identity is unresolved"
    restored = sp.ImmutableMatrix(matrix.xreplace(reverse))
    rank = (
        analyze_symbolic_rank(
            restored, conditions=normalized.conditions, max_minors=max_minors
        )
        if status is _core.AffineStatus.AFFINE
        else None
    )
    return ImplicitDAEStructure(
        normalized,
        rates,
        tuple(sp.Derivative(v, source.time) for v in source.inputs),
        status,
        restored,
        sp.ImmutableMatrix(offset.xreplace(reverse)),
        rank,
        reason,
    )


def verify_implicit_structure(analysis):
    failed = _core.CertificateStatus.FAILED
    if not isinstance(analysis, ImplicitDAEStructure):
        return _core.CertificateVerification(failed, ("invalid DAE structure record",))
    try:
        expected = analyze_implicit_dae(
            analysis.normalization.source,
            max_minors=analysis.rank.max_minors if analysis.rank else 64,
        )
    except (InvalidSystemError, ValueError, TypeError, AttributeError) as exc:
        return _core.CertificateVerification(failed, (str(exc),))
    if analysis != expected:
        return _core.CertificateVerification(
            failed, ("normalization, mass matrix or rank certificate mismatch",)
        )
    return _core.CertificateVerification(_core.CertificateStatus.VERIFIED)
