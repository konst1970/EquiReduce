"""Exact symbolic reduction primitives for static algebraic residual systems.

This module provides conservative affine detection, greedy single-variable
elimination, exact full-rank affine-block elimination, and algebraic
certificate verification. Lean export and audit-artifact generation are
implemented in adjacent modules.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import sympy as sp

from equireduce.conditions import (
    assumption_consistency,
    normalize_conditions,
    simplify_condition,
)
from equireduce.errors import CertificateError as SymbolicReductionError
from equireduce.errors import UnsupportedDomainError as UnsupportedReductionDomainError
from equireduce.system import System as ResidualSystem


class SymbolicZeroStatus(Enum):
    """Whether an expression is identically zero, not, or unresolved."""

    ZERO = "zero"
    NOT_IDENTICALLY_ZERO = "not_identically_zero"
    UNKNOWN = "unknown"


class AffineStatus(Enum):
    """Outcome of checking affinity in a selected set of variables."""

    AFFINE = "affine"
    NON_AFFINE = "non_affine"
    UNKNOWN = "unknown"


class CertificateStatus(Enum):
    """Outcome of checking an algebraic reduction certificate."""

    VERIFIED = "verified"
    FAILED = "failed"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class AffineDecomposition:
    """Exact ``A*y + b`` form, or a conservative failure status."""

    status: AffineStatus
    variables: tuple[sp.Symbol, ...]
    coefficients: sp.ImmutableMatrix | None
    offset: sp.ImmutableMatrix | None
    reason: str | None = None


def symbolic_zero_status(expression: sp.Expr) -> SymbolicZeroStatus:
    """Classify identity with zero, not identity with zero, or unresolved.

    Undefined functions and unevaluated derivatives are intentionally not
    assigned a nonzero result: SymPy does not know their defining laws. The
    not-identically-zero status does not mean the expression has no roots.
    """
    try:
        candidate = sp.simplify(sp.sympify(expression))
    except (ArithmeticError, NotImplementedError, TypeError, ValueError):
        return SymbolicZeroStatus.UNKNOWN

    if candidate == 0 or candidate.is_zero is True:
        return SymbolicZeroStatus.ZERO
    if candidate.has(sp.core.function.AppliedUndef, sp.Derivative):
        return SymbolicZeroStatus.UNKNOWN
    if candidate.is_zero is False:
        return SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
    # Expr.equals may use numerical probing. A nonzero exact polynomial
    # coefficient is instead a symbolic witness of nonidentity.
    symbols = sorted(candidate.free_symbols, key=sp.srepr)
    if symbols:
        try:
            numerator, _ = sp.cancel(candidate).as_numer_denom()
            polynomial = sp.Poly(numerator, *symbols, domain="EX")
            if any(coefficient.is_zero is False for coefficient in polynomial.coeffs()):
                return SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
            if polynomial.is_zero:
                return SymbolicZeroStatus.ZERO
        except (sp.PolynomialError, ValueError, TypeError):
            pass
        # A nonconstant rational argument varies on a real open domain; its
        # sine/cosine cannot vanish identically. Do not extend this rule to
        # arbitrary opaque functions or unresolved trigonometric identities.
        _, factor = candidate.as_coeff_Mul()
        if factor.func in (sp.sin, sp.cos):
            argument = factor.args[0]
            if argument.free_symbols and argument.is_rational_function(*symbols):
                return SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
    return SymbolicZeroStatus.UNKNOWN


def _nonpolynomial_affinity_status(
    expressions: tuple[sp.Expr, ...], variables: tuple[sp.Symbol, ...]
) -> tuple[AffineStatus, str]:
    """Use exact second derivatives when polynomial extraction is unavailable."""
    unresolved = False
    for expression in expressions:
        for left in variables:
            for right in variables:
                status = symbolic_zero_status(sp.diff(expression, left, right))
                if status is SymbolicZeroStatus.NOT_IDENTICALLY_ZERO:
                    return AffineStatus.NON_AFFINE, (
                        "a second partial derivative is provably nonzero"
                    )
                unresolved |= status is SymbolicZeroStatus.UNKNOWN
    if unresolved:
        return AffineStatus.UNKNOWN, (
            "non-polynomial dependence could not be classified exactly"
        )
    return AffineStatus.AFFINE, "second partial derivatives vanish"


def decompose_affine_system(
    residuals: tuple[sp.Expr, ...] | list[sp.Expr],
    variables: tuple[sp.Symbol, ...] | list[sp.Symbol],
) -> AffineDecomposition:
    """Find exact coefficients and offsets for affinity in ``variables``.

    Coefficients may be arbitrary SymPy expressions in all other symbols. If
    affinity cannot be established, no partial coefficient matrix is returned.
    """
    expressions = tuple(sp.sympify(residual) for residual in residuals)
    selected = tuple(variables)
    if any(not isinstance(variable, sp.Symbol) for variable in selected):
        raise TypeError("affine variables must be SymPy Symbols")
    if len(set(selected)) != len(selected):
        raise ValueError("affine variables must be unique")

    if not selected:
        return AffineDecomposition(
            AffineStatus.AFFINE,
            selected,
            sp.ImmutableMatrix(len(expressions), 0, []),
            sp.ImmutableMatrix(len(expressions), 1, expressions),
        )

    rows: list[list[sp.Expr]] = []
    offsets: list[sp.Expr] = []
    try:
        polynomials = [sp.Poly(expr, *selected, domain="EX") for expr in expressions]
    except sp.PolynomialError:
        status, reason = _nonpolynomial_affinity_status(expressions, selected)
        if status is not AffineStatus.AFFINE:
            return AffineDecomposition(status, selected, None, None, reason)
        # Affine non-polynomial expressions are uncommon (for example, a
        # Piecewise expression independent of the selected variables). Recover
        # coefficients by differentiation and verify the complete identity.
        rows = [
            [sp.diff(expr, variable) for variable in selected] for expr in expressions
        ]
        offsets = [
            sp.simplify(
                expr
                - sum(
                    coefficient * variable
                    for coefficient, variable in zip(row, selected, strict=True)
                )
            )
            for expr, row in zip(expressions, rows, strict=True)
        ]
    else:
        for polynomial in polynomials:
            coefficients = [sp.S.Zero] * len(selected)
            offset = sp.S.Zero
            for powers, coefficient in polynomial.terms():
                degree = sum(powers)
                if degree > 1:
                    return AffineDecomposition(
                        AffineStatus.NON_AFFINE,
                        selected,
                        None,
                        None,
                        "a polynomial term has degree greater than one",
                    )
                if degree == 0:
                    offset += coefficient
                else:
                    index = powers.index(1)
                    coefficients[index] += coefficient
            rows.append(coefficients)
            offsets.append(offset)

    rows = [[sp.simplify(value) for value in row] for row in rows]
    offsets = [sp.simplify(value) for value in offsets]
    if any(value.has(*selected) for row in rows for value in row) or any(
        value.has(*selected) for value in offsets
    ):
        return AffineDecomposition(
            AffineStatus.UNKNOWN,
            selected,
            None,
            None,
            "a coefficient or offset may still depend on selected variables",
        )

    coefficient_matrix = sp.ImmutableMatrix(rows)
    offset_matrix = sp.ImmutableMatrix(offsets)
    for expression, row, offset in zip(expressions, rows, offsets, strict=True):
        reconstructed = (
            sum(
                coefficient * variable
                for coefficient, variable in zip(row, selected, strict=True)
            )
            + offset
        )
        identity_status = symbolic_zero_status(expression - reconstructed)
        if identity_status is SymbolicZeroStatus.NOT_IDENTICALLY_ZERO:
            return AffineDecomposition(
                AffineStatus.NON_AFFINE,
                selected,
                None,
                None,
                "affine reconstruction identity is false",
            )
        if identity_status is SymbolicZeroStatus.UNKNOWN:
            return AffineDecomposition(
                AffineStatus.UNKNOWN,
                selected,
                None,
                None,
                "affine reconstruction identity is unresolved",
            )

    return AffineDecomposition(
        AffineStatus.AFFINE, selected, coefficient_matrix, offset_matrix
    )


@dataclass(frozen=True)
class ReductionStep:
    """One exact elimination step and its required nonzero pivot condition."""

    equation_index: int
    equation_name: str
    variable: sp.Expr
    coefficient: sp.Expr
    remainder: sp.Expr
    guard: sp.Expr
    pivot_residual: sp.Expr | None = None
    prior_substitutions: tuple[tuple[sp.Expr, sp.Expr], ...] = ()

    def __post_init__(self) -> None:
        if self.equation_index < 0:
            raise ValueError("equation_index must be nonnegative")
        for field_name in ("variable", "coefficient", "remainder", "guard"):
            object.__setattr__(self, field_name, sp.sympify(getattr(self, field_name)))
        if self.pivot_residual is not None:
            object.__setattr__(self, "pivot_residual", sp.sympify(self.pivot_residual))
        object.__setattr__(
            self,
            "prior_substitutions",
            tuple(
                (sp.sympify(variable), sp.sympify(expression))
                for variable, expression in self.prior_substitutions
            ),
        )

    @property
    def reconstruction_expression(self) -> sp.Expr:
        """Return the eliminated variable as an exact symbolic expression."""
        return -self.remainder / self.coefficient


@dataclass(frozen=True)
class ReductionBlockStep:
    """One exact square affine-block elimination and its pivot conditions."""

    equation_indices: tuple[int, ...]
    equation_names: tuple[str, ...]
    variables: tuple[sp.Symbol, ...]
    coefficient_matrix: sp.ImmutableMatrix
    offset: sp.ImmutableMatrix
    determinant: sp.Expr
    guards: tuple[sp.Expr, ...]
    reconstruction: tuple[tuple[sp.Symbol, sp.Expr], ...]
    pivot_residuals: tuple[sp.Expr, ...]
    prior_substitutions: tuple[tuple[sp.Expr, sp.Expr], ...] = ()


@dataclass(frozen=True)
class ReductionResult:
    """Immutable symbolic reduction output with source and reconstruction data.

    ``source_*`` fields snapshot the input system so the reduction can later be
    checked independently. The reduced equations remain implicit; this result
    never implies that a nonlinear system has been solved.
    """

    source_domain: str
    source_unknowns: tuple[sp.Expr, ...]
    source_residuals: tuple[sp.Expr, ...]
    source_residual_names: tuple[str, ...]
    reduced_unknowns: tuple[sp.Expr, ...]
    reduced_residuals: tuple[sp.Expr, ...]
    reduced_residual_indices: tuple[int, ...]
    eliminated_unknowns: tuple[sp.Expr, ...]
    reconstruction: tuple[tuple[sp.Expr, sp.Expr], ...]
    conditions: tuple[sp.Expr, ...]
    steps: tuple[ReductionStep | ReductionBlockStep, ...]
    stopping_reason: str = "no_affine_single_variable_equation"

    def __post_init__(self) -> None:
        tuple_fields = (
            "source_unknowns",
            "source_residuals",
            "source_residual_names",
            "reduced_unknowns",
            "reduced_residuals",
            "reduced_residual_indices",
            "eliminated_unknowns",
            "reconstruction",
            "conditions",
            "steps",
        )
        for field_name in tuple_fields:
            object.__setattr__(self, field_name, tuple(getattr(self, field_name)))

        if self.source_domain != "algebraic":
            raise UnsupportedReductionDomainError(
                "symbolic reduction currently supports only the algebraic domain"
            )
        if len(self.source_residual_names) not in (0, len(self.source_residuals)):
            raise ValueError("source residual names must match source residuals")
        if len(self.reduced_residual_indices) != len(self.reduced_residuals):
            raise ValueError("reduced residual indices must match reduced residuals")
        if any(
            index < 0 or index >= len(self.source_residuals)
            for index in self.reduced_residual_indices
        ) or len(set(self.reduced_residual_indices)) != len(
            self.reduced_residual_indices
        ):
            raise ValueError("reduced residual indices must be unique source indices")

        source = self.source_unknowns
        reduced = self.reduced_unknowns
        eliminated = self.eliminated_unknowns
        if len(set(source)) != len(source):
            raise ValueError("source unknowns must be unique")
        if len(set(reduced)) != len(reduced) or len(set(eliminated)) != len(eliminated):
            raise ValueError("reduced and eliminated unknowns must be unique")
        if set(reduced).intersection(eliminated) or set(reduced).union(
            eliminated
        ) != set(source):
            raise ValueError(
                "reduced and eliminated unknowns must partition source unknowns"
            )

        reconstruction = tuple(
            (sp.sympify(variable), sp.sympify(expression))
            for variable, expression in self.reconstruction
        )
        object.__setattr__(self, "reconstruction", reconstruction)
        reconstructed_variables = tuple(variable for variable, _ in reconstruction)
        if len(set(reconstructed_variables)) != len(reconstructed_variables):
            raise ValueError("reconstruction variables must be unique")
        if set(reconstructed_variables) != set(eliminated):
            raise ValueError("reconstruction must define every eliminated unknown")

        for field_name in (
            "source_residuals",
            "reduced_residuals",
            "conditions",
        ):
            object.__setattr__(
                self,
                field_name,
                tuple(sp.sympify(value) for value in getattr(self, field_name)),
            )


@dataclass(frozen=True)
class ResidualRewrite:
    """Image of one source residual under the complete reconstruction map."""

    source_index: int
    source_name: str
    substituted_residual: sp.Expr
    reduced_index: int | None


@dataclass(frozen=True)
class ReductionCertificate:
    """Algebraic trace tying source equations to a reduced system."""

    source_unknowns: tuple[sp.Expr, ...]
    source_residuals: tuple[sp.Expr, ...]
    source_residual_names: tuple[str, ...]
    reduced_unknowns: tuple[sp.Expr, ...]
    reduced_residuals: tuple[sp.Expr, ...]
    reduced_residual_indices: tuple[int, ...]
    reconstruction: tuple[tuple[sp.Expr, sp.Expr], ...]
    conditions: tuple[sp.Expr, ...]
    steps: tuple[ReductionStep | ReductionBlockStep, ...]
    residual_rewrites: tuple[ResidualRewrite, ...]


@dataclass(frozen=True)
class CertificateVerification:
    """Result of checking every identity and trace in a reduction certificate."""

    status: CertificateStatus
    failures: tuple[str, ...] = ()
    unresolved: tuple[str, ...] = ()


def validate_dc_system(system: ResidualSystem) -> ResidualSystem:
    """Validate the input-domain boundary for algebraic-only symbolic reduction."""
    if system.domain != "algebraic":
        raise UnsupportedReductionDomainError(
            "symbolic reduction currently supports only algebraic residual systems"
        )
    if len(set(system.unknowns)) != len(system.unknowns):
        raise SymbolicReductionError(
            "algebraic residual system unknowns must be unique"
        )
    return system


def _validate_candidates(
    source_unknowns: tuple[sp.Expr, ...],
    candidates: tuple[sp.Expr, ...] | list[sp.Expr] | None,
) -> tuple[sp.Expr, ...]:
    selected = tuple(source_unknowns if candidates is None else candidates)
    if len(set(selected)) != len(selected):
        raise ValueError("elimination candidates must be unique")
    if not set(selected).issubset(source_unknowns):
        raise ValueError("elimination candidates must be source unknowns")
    return selected


def _find_singleton_pivot(rows, candidates, eliminated):
    for row_index, (source_index, name, residual) in enumerate(rows):
        occurring = [
            variable
            for variable in candidates
            if variable not in eliminated and residual.has(variable)
        ]
        if len(occurring) != 1:
            continue

        variable = occurring[0]
        decomposition = decompose_affine_system((residual,), (variable,))
        if decomposition.status is not AffineStatus.AFFINE:
            continue
        assert decomposition.coefficients is not None
        assert decomposition.offset is not None
        coefficient = decomposition.coefficients[0, 0]
        if (
            symbolic_zero_status(coefficient)
            is not SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
        ):
            continue
        remainder = decomposition.offset[0, 0]
        return row_index, source_index, name, variable, coefficient, remainder
    return None


def _affine_components(rows, candidates):
    """Build deterministic connected components of the affine incidence graph."""
    row_variables: dict[int, list[sp.Symbol]] = {}
    variable_rows: dict[sp.Symbol, list[int]] = {
        variable: [] for variable in candidates
    }
    for row_index, (_, _, residual) in enumerate(rows):
        for variable in candidates:
            decomposition = decompose_affine_system((residual,), (variable,))
            if decomposition.status is not AffineStatus.AFFINE:
                continue
            assert decomposition.coefficients is not None
            coefficient = decomposition.coefficients[0, 0]
            if (
                symbolic_zero_status(coefficient)
                is not SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
            ):
                continue
            row_variables.setdefault(row_index, []).append(variable)
            variable_rows[variable].append(row_index)

    components = []
    visited_rows: set[int] = set()
    for seed in sorted(row_variables):
        if seed in visited_rows:
            continue
        component_rows: set[int] = set()
        component_variables: set[sp.Symbol] = set()
        pending_rows = [seed]
        while pending_rows:
            row_index = pending_rows.pop()
            if row_index in component_rows:
                continue
            component_rows.add(row_index)
            visited_rows.add(row_index)
            for variable in row_variables[row_index]:
                if variable in component_variables:
                    continue
                component_variables.add(variable)
                pending_rows.extend(variable_rows[variable])
        components.append(
            (
                tuple(sorted(component_rows)),
                tuple(
                    variable
                    for variable in candidates
                    if variable in component_variables
                ),
            )
        )
    return components


def _denominator_guards(expressions: tuple[sp.Expr, ...]) -> tuple[sp.Expr, ...] | None:
    """Return nonzero conditions needed for rational expressions to exist."""
    guards = []
    for expression in expressions:
        denominator = sp.factor(sp.together(expression).as_numer_denom()[1])
        if denominator == 1:
            continue
        if symbolic_zero_status(denominator) is SymbolicZeroStatus.ZERO:
            return None
        guard = sp.Ne(denominator, 0)
        if guard is not sp.true:
            guards.append(guard)
    return tuple(dict.fromkeys(guards))


def _find_affine_block(rows, candidates, eliminated):
    remaining = tuple(variable for variable in candidates if variable not in eliminated)
    for component_rows, component_variables in _affine_components(rows, remaining):
        # Nonlinear equations sharing a variable are retained as remainders;
        # they must not prevent a separate affine subsystem from being solved.
        component_rows = tuple(
            index
            for index in component_rows
            if decompose_affine_system((rows[index][2],), component_variables).status
            is AffineStatus.AFFINE
        )
        if not component_rows:
            continue
        expressions = tuple(rows[index][2] for index in component_rows)
        decomposition = decompose_affine_system(expressions, component_variables)
        if decomposition.status is not AffineStatus.AFFINE:
            continue

        coefficients = sp.Matrix(decomposition.coefficients)
        try:
            column_pivots = coefficients.rref()[1]
            rank = len(column_pivots)
            if rank == 0:
                continue
            independent_columns = tuple(column_pivots[:rank])
            selected_columns = coefficients[:, independent_columns]
            row_pivots = selected_columns.T.rref()[1]
            if len(row_pivots) < rank:
                continue
            independent_rows = tuple(row_pivots[:rank])
        except (ArithmeticError, NotImplementedError, ValueError, ZeroDivisionError):
            continue

        square = coefficients.extract(independent_rows, independent_columns)
        determinant = sp.cancel(square.det())
        if (
            symbolic_zero_status(determinant)
            is not SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
        ):
            continue
        selected_variables = tuple(
            component_variables[index] for index in independent_columns
        )
        retained_column_indices = tuple(
            index
            for index in range(len(component_variables))
            if index not in independent_columns
        )
        effective_offset = sp.Matrix(decomposition.offset)
        if retained_column_indices:
            retained_coefficients = coefficients[:, retained_column_indices]
            retained_values = sp.Matrix(
                [component_variables[index] for index in retained_column_indices]
            )
            effective_offset += retained_coefficients * retained_values
        offset = effective_offset.extract(independent_rows, [0])
        selected_rows = tuple(component_rows[index] for index in independent_rows)
        try:
            solution, parameters = square.gauss_jordan_solve(-offset)
        except (ArithmeticError, NotImplementedError, ValueError, ZeroDivisionError):
            continue
        if parameters.rows:
            continue
        solution_values = tuple(sp.cancel(value) for value in solution)
        if any(value.has(*selected_variables) for value in solution_values):
            continue

        guards = []
        determinant_guard = sp.Ne(determinant, 0)
        if not (determinant.is_number and determinant_guard is sp.true):
            guards.append(determinant_guard)
        domain_guards = _denominator_guards(
            tuple(square) + tuple(offset) + (determinant,)
        )
        if domain_guards is None:
            continue
        guards.extend(domain_guards)
        safe = True
        for value in solution_values:
            denominator = sp.factor(sp.together(value).as_numer_denom()[1])
            if denominator == 1:
                continue
            if (
                symbolic_zero_status(denominator - determinant)
                is SymbolicZeroStatus.ZERO
                or symbolic_zero_status(denominator + determinant)
                is SymbolicZeroStatus.ZERO
            ):
                continue
            if (
                symbolic_zero_status(denominator)
                is not SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
            ):
                safe = False
                break
            denominator_guard = sp.Ne(denominator, 0)
            if not (denominator.is_number and denominator_guard is sp.true):
                guards.append(denominator_guard)
        if not safe:
            continue

        substitutions = dict(zip(selected_variables, solution_values, strict=True))
        if any(
            symbolic_zero_status(
                rows[row_index][2].subs(substitutions, simultaneous=True)
            )
            is not SymbolicZeroStatus.ZERO
            for row_index in selected_rows
        ):
            continue

        return (
            selected_rows,
            tuple(rows[index][0] for index in selected_rows),
            tuple(rows[index][1] for index in selected_rows),
            tuple(rows[index][2] for index in selected_rows),
            selected_variables,
            sp.ImmutableMatrix(square),
            sp.ImmutableMatrix(offset),
            determinant,
            tuple(dict.fromkeys(guards)),
            tuple(zip(selected_variables, solution_values, strict=True)),
        )
    return None


def _reduce(
    system: ResidualSystem,
    *,
    candidates: tuple[sp.Expr, ...] | list[sp.Expr] | None,
    allow_blocks: bool,
) -> ReductionResult:
    validate_dc_system(system)
    source_unknowns = tuple(system.unknowns)
    selected = _validate_candidates(source_unknowns, candidates)
    residual_names = tuple(system.residual_names)
    rows = [
        (
            index,
            residual_names[index] if index < len(residual_names) else f"F{index}",
            sp.sympify(residual),
        )
        for index, residual in enumerate(system.residuals)
    ]
    eliminated: set[sp.Expr] = set()
    reconstruction: dict[sp.Expr, sp.Expr] = {}
    conditions: list[sp.Expr] = list(system.conditions)
    steps: list[ReductionStep | ReductionBlockStep] = []

    while True:
        singleton = _find_singleton_pivot(rows, selected, eliminated)
        if singleton is not None:
            (
                row_index,
                source_index,
                name,
                variable,
                coefficient,
                remainder,
            ) = singleton
            value = sp.cancel(-remainder / coefficient)
            guard = sp.Ne(coefficient, 0)
            domain_guards = _denominator_guards((coefficient, remainder, value))
            if domain_guards is None:
                break
            prior_substitutions = tuple(
                (source_variable, reconstruction[source_variable])
                for source_variable in source_unknowns
                if source_variable in reconstruction
            )
            steps.append(
                ReductionStep(
                    equation_index=source_index,
                    equation_name=name,
                    variable=variable,
                    coefficient=coefficient,
                    remainder=remainder,
                    guard=guard,
                    pivot_residual=rows[row_index][2],
                    prior_substitutions=prior_substitutions,
                )
            )
            substitutions = {variable: value}
            pending_guards = list(domain_guards)
            if not (coefficient.is_number and guard is sp.true):
                pending_guards.append(guard)
            new_guards = tuple(dict.fromkeys(pending_guards))
        elif allow_blocks:
            block = _find_affine_block(rows, selected, eliminated)
            if block is None:
                break
            (
                selected_rows,
                equation_indices,
                equation_names,
                pivot_residuals,
                variables,
                coefficient_matrix,
                offset,
                determinant,
                new_guards,
                block_reconstruction,
            ) = block
            substitutions = dict(block_reconstruction)
            prior_substitutions = tuple(
                (source_variable, reconstruction[source_variable])
                for source_variable in source_unknowns
                if source_variable in reconstruction
            )
            steps.append(
                ReductionBlockStep(
                    equation_indices=equation_indices,
                    equation_names=equation_names,
                    variables=variables,
                    coefficient_matrix=coefficient_matrix,
                    offset=offset,
                    determinant=determinant,
                    guards=new_guards,
                    reconstruction=block_reconstruction,
                    pivot_residuals=pivot_residuals,
                    prior_substitutions=prior_substitutions,
                )
            )
            row_indices_to_remove = set(selected_rows)
        else:
            break

        trial_conditions = [
            condition.subs(substitutions, simultaneous=True)
            for condition in (*conditions, *new_guards)
        ]
        if assumption_consistency(trial_conditions) == "inconsistent":
            steps.pop()
            break

        for eliminated_variable, expression in tuple(reconstruction.items()):
            reconstruction[eliminated_variable] = sp.cancel(
                expression.subs(substitutions, simultaneous=True)
            )
        conditions = [
            simplify_condition(condition.subs(substitutions, simultaneous=True))
            for condition in conditions
        ]
        conditions.extend(guard for guard in new_guards if guard is not sp.true)
        reconstruction.update(substitutions)
        eliminated.update(substitutions)

        if singleton is not None:
            row_indices_to_remove = {row_index}
        next_rows = []
        for index, row in enumerate(rows):
            if index in row_indices_to_remove:
                continue
            source_index, name, expression = row
            substituted = expression.subs(substitutions, simultaneous=True)
            if symbolic_zero_status(substituted) is SymbolicZeroStatus.ZERO:
                continue
            next_rows.append((source_index, name, substituted))
        rows = next_rows

    reconstruction_items = tuple(
        (variable, reconstruction[variable])
        for variable in source_unknowns
        if variable in reconstruction
    )
    reduced_unknowns = tuple(
        variable for variable in source_unknowns if variable not in eliminated
    )
    remaining_candidates = set(selected) - eliminated
    if not remaining_candidates:
        stopping_reason = "all_candidates_eliminated"
    elif allow_blocks:
        stopping_reason = "no_full_rank_affine_block"
    else:
        stopping_reason = "no_affine_single_variable_equation"
    return ReductionResult(
        source_domain="algebraic",
        source_unknowns=source_unknowns,
        source_residuals=tuple(system.residuals),
        source_residual_names=residual_names,
        reduced_unknowns=reduced_unknowns,
        reduced_residuals=tuple(expression for _, _, expression in rows),
        reduced_residual_indices=tuple(source_index for source_index, _, _ in rows),
        eliminated_unknowns=tuple(
            variable for variable in source_unknowns if variable in eliminated
        ),
        reconstruction=reconstruction_items,
        conditions=tuple(dict.fromkeys(conditions)),
        steps=tuple(steps),
        stopping_reason=stopping_reason,
    )


def reduce_affine_singletons(
    system: ResidualSystem,
    *,
    candidates: tuple[sp.Expr, ...] | list[sp.Expr] | None = None,
) -> ReductionResult:
    """Eliminate variables found alone and affinely in a algebraic residual."""
    return _reduce(system, candidates=candidates, allow_blocks=False)


def reduce_affine_system(
    system: ResidualSystem,
    *,
    candidates: tuple[sp.Expr, ...] | list[sp.Expr] | None = None,
) -> ReductionResult:
    """Apply singleton elimination, then exact affine-block elimination.

    The method preserves all nonlinear residuals and their source names. It
    returns a partial reduction if no square full-rank affine block is found.
    """
    return _reduce(system, candidates=candidates, allow_blocks=True)


def build_reduction_certificate(result: ReductionResult) -> ReductionCertificate:
    """Build a source-to-reduced residual trace from a reduction result."""
    substitutions = dict(result.reconstruction)
    reduced_positions = {
        source_index: reduced_index
        for reduced_index, source_index in enumerate(result.reduced_residual_indices)
    }
    names = result.source_residual_names
    rewrites = tuple(
        ResidualRewrite(
            source_index=index,
            source_name=names[index] if names else f"F{index}",
            substituted_residual=sp.cancel(
                residual.subs(substitutions, simultaneous=True)
            ),
            reduced_index=reduced_positions.get(index),
        )
        for index, residual in enumerate(result.source_residuals)
    )
    return ReductionCertificate(
        source_unknowns=result.source_unknowns,
        source_residuals=result.source_residuals,
        source_residual_names=result.source_residual_names,
        reduced_unknowns=result.reduced_unknowns,
        reduced_residuals=result.reduced_residuals,
        reduced_residual_indices=result.reduced_residual_indices,
        reconstruction=result.reconstruction,
        conditions=result.conditions,
        steps=result.steps,
        residual_rewrites=rewrites,
    )


def verify_reduction_certificate(
    result: ReductionResult,
    certificate: ReductionCertificate | None = None,
) -> CertificateVerification:
    """Check the reduction trace and both reconstruction directions' identities.

    This verifies the algebraic certificate in SymPy. For formal verification
    of the same reduction, use ``verify_reduction_with_lean``.
    """
    certificate = certificate or build_reduction_certificate(result)
    failures: list[str] = []
    unresolved: list[str] = []

    expected_fields = (
        "source_unknowns",
        "source_residuals",
        "source_residual_names",
        "reduced_unknowns",
        "reduced_residuals",
        "reduced_residual_indices",
        "reconstruction",
        "conditions",
        "steps",
    )
    for field_name in expected_fields:
        if getattr(certificate, field_name) != getattr(result, field_name):
            failures.append(f"certificate {field_name} does not match the result")
    if failures:
        return CertificateVerification(CertificateStatus.FAILED, tuple(failures))

    final_substitutions = dict(certificate.reconstruction)

    def require_condition(condition: sp.Expr, label: str) -> None:
        normalized = simplify_condition(
            condition.subs(final_substitutions, simultaneous=True)
        )
        required = normalize_conditions((normalized,))
        if any(
            value not in normalize_conditions(result.conditions) for value in required
        ):
            failures.append(label)

    def check_identity(expression: sp.Expr, label: str) -> None:
        if isinstance(expression, sp.MatrixBase):
            statuses = [symbolic_zero_status(entry) for entry in expression]
            if any(
                status is SymbolicZeroStatus.NOT_IDENTICALLY_ZERO for status in statuses
            ):
                failures.append(label)
            elif any(status is SymbolicZeroStatus.UNKNOWN for status in statuses):
                unresolved.append(label)
            return
        status = symbolic_zero_status(expression)
        if status is SymbolicZeroStatus.NOT_IDENTICALLY_ZERO:
            failures.append(label)
        elif status is SymbolicZeroStatus.UNKNOWN:
            unresolved.append(label)

    accumulated: dict[sp.Expr, sp.Expr] = {}
    source_names = result.source_residual_names
    for step_number, step in enumerate(certificate.steps):
        expected_prior = tuple(
            (variable, accumulated[variable])
            for variable in result.source_unknowns
            if variable in accumulated
        )
        if step.prior_substitutions != expected_prior:
            failures.append(
                f"step {step_number} has an incorrect prior substitution map"
            )
            continue
        prior = dict(step.prior_substitutions)

        if isinstance(step, ReductionStep):
            if step.pivot_residual is None:
                failures.append(f"step {step_number} is missing its pivot residual")
                continue
            if not 0 <= step.equation_index < len(result.source_residuals):
                failures.append(
                    f"step {step_number} has an invalid source equation index"
                )
                continue
            name = (
                source_names[step.equation_index]
                if source_names
                else f"F{step.equation_index}"
            )
            if name != step.equation_name:
                failures.append(
                    f"step {step_number} source equation name does not match"
                )
            source_image = result.source_residuals[step.equation_index].subs(
                prior, simultaneous=True
            )
            check_identity(
                source_image - step.pivot_residual,
                f"step {step_number} pivot is not the recorded source residual",
            )
            check_identity(
                step.pivot_residual
                - (step.coefficient * step.variable + step.remainder),
                f"step {step_number} affine pivot identity failed",
            )
            if step.coefficient.has(step.variable) or step.remainder.has(step.variable):
                failures.append(f"step {step_number} coefficient is not affine")
            expected_guard = sp.Ne(step.coefficient, 0)
            if step.guard != expected_guard:
                failures.append(f"step {step_number} pivot guard does not match")
            value = step.reconstruction_expression
            check_identity(
                step.coefficient * value + step.remainder,
                f"step {step_number} reconstruction does not solve its pivot",
            )
            for denominator_guard in (
                _denominator_guards((step.coefficient, step.remainder, value)) or ()
            ):
                require_condition(
                    denominator_guard,
                    f"step {step_number} is missing a denominator condition",
                )
            if step.guard is not sp.true:
                require_condition(
                    step.guard,
                    f"step {step_number} is missing its pivot condition",
                )
            substitutions = {step.variable: value}
        else:
            size = len(step.variables)
            if (
                len(step.equation_indices) != size
                or len(step.equation_names) != size
                or len(step.pivot_residuals) != size
                or step.coefficient_matrix.shape != (size, size)
                or step.offset.shape != (size, 1)
                or len(step.reconstruction) != size
            ):
                failures.append(f"step {step_number} block dimensions do not match")
                continue
            if len(set(step.variables)) != size:
                failures.append(f"step {step_number} block variables are not unique")
            for equation_index, equation_name, pivot_residual in zip(
                step.equation_indices,
                step.equation_names,
                step.pivot_residuals,
                strict=True,
            ):
                if not 0 <= equation_index < len(result.source_residuals):
                    failures.append(
                        f"step {step_number} has an invalid source equation index"
                    )
                    continue
                name = (
                    source_names[equation_index]
                    if source_names
                    else f"F{equation_index}"
                )
                if name != equation_name:
                    failures.append(
                        f"step {step_number} source equation name does not match"
                    )
                source_image = result.source_residuals[equation_index].subs(
                    prior, simultaneous=True
                )
                check_identity(
                    source_image - pivot_residual,
                    f"step {step_number} block pivot does not match "
                    "its source equation",
                )
            variables_vector = sp.Matrix(step.variables)
            pivot_vector = sp.Matrix(step.pivot_residuals)
            check_identity(
                sp.Matrix(step.coefficient_matrix) * variables_vector
                + sp.Matrix(step.offset)
                - pivot_vector,
                f"step {step_number} block affine identity failed",
            )
            if any(
                entry.has(*step.variables)
                for entry in (*step.coefficient_matrix, *step.offset)
            ):
                failures.append(
                    f"step {step_number} block coefficients depend on "
                    "eliminated variables"
                )
            matrix_determinant = sp.cancel(step.coefficient_matrix.det())
            check_identity(
                step.determinant - matrix_determinant,
                f"step {step_number} block determinant does not match",
            )
            substitutions = dict(step.reconstruction)
            if tuple(substitutions) != step.variables:
                failures.append(
                    f"step {step_number} block reconstruction order differs"
                )
            solution_vector = sp.Matrix(
                [substitutions.get(variable, sp.nan) for variable in step.variables]
            )
            check_identity(
                sp.Matrix(step.coefficient_matrix) * solution_vector
                + sp.Matrix(step.offset),
                f"step {step_number} block reconstruction does not solve its pivot",
            )
            if (
                symbolic_zero_status(step.determinant)
                is not SymbolicZeroStatus.NOT_IDENTICALLY_ZERO
            ):
                failures.append(
                    f"step {step_number} determinant is not proved nonzero generically"
                )
            if sp.Ne(step.determinant, 0) not in step.guards and not (
                step.determinant.is_number and sp.Ne(step.determinant, 0) is sp.true
            ):
                failures.append(
                    f"step {step_number} block determinant guard is missing"
                )
            for guard in step.guards:
                require_condition(
                    guard,
                    f"step {step_number} block condition is missing",
                )

        for variable, expression in tuple(accumulated.items()):
            accumulated[variable] = sp.cancel(
                expression.subs(substitutions, simultaneous=True)
            )
        for variable, expression in substitutions.items():
            if variable in accumulated:
                failures.append(f"step {step_number} eliminates a variable twice")
            accumulated[variable] = sp.cancel(expression)

    actual_reconstruction = dict(certificate.reconstruction)
    if set(actual_reconstruction) != set(accumulated):
        failures.append("final reconstruction variables do not match the step trace")
    else:
        for variable, expression in actual_reconstruction.items():
            check_identity(
                expression - accumulated[variable],
                f"final reconstruction for {variable} does not match the step trace",
            )

    if len(certificate.residual_rewrites) != len(result.source_residuals):
        failures.append("certificate does not contain one rewrite per source residual")
    else:
        substitutions = dict(certificate.reconstruction)
        reduced_by_source = {
            source_index: reduced_index
            for reduced_index, source_index in enumerate(
                certificate.reduced_residual_indices
            )
        }
        covered_reduced: set[int] = set()
        for source_index, rewrite in enumerate(certificate.residual_rewrites):
            if rewrite.source_index != source_index:
                failures.append("source residual rewrites are not in source order")
                continue
            expected_name = (
                source_names[source_index] if source_names else f"F{source_index}"
            )
            if rewrite.source_name != expected_name:
                failures.append(f"source residual {source_index} name does not match")
            source_image = sp.cancel(
                result.source_residuals[source_index].subs(
                    substitutions, simultaneous=True
                )
            )
            check_identity(
                source_image - rewrite.substituted_residual,
                f"source residual {source_index} rewrite is incorrect",
            )
            expected_reduced_index = reduced_by_source.get(source_index)
            if rewrite.reduced_index != expected_reduced_index:
                failures.append(
                    f"source residual {source_index} reduced index does not match"
                )
            if expected_reduced_index is None:
                check_identity(
                    rewrite.substituted_residual,
                    f"source residual {source_index} should reduce to zero",
                )
            else:
                covered_reduced.add(expected_reduced_index)
                check_identity(
                    rewrite.substituted_residual
                    - certificate.reduced_residuals[expected_reduced_index],
                    f"source residual {source_index} does not match "
                    "its reduced equation",
                )
        if covered_reduced != set(range(len(certificate.reduced_residuals))):
            failures.append("not every reduced residual is linked to a source equation")

    if failures:
        return CertificateVerification(
            CertificateStatus.FAILED, tuple(failures), tuple(unresolved)
        )
    if unresolved:
        return CertificateVerification(CertificateStatus.UNKNOWN, (), tuple(unresolved))
    return CertificateVerification(CertificateStatus.VERIFIED)
