"""Immutable real algebraic systems represented directly by SymPy objects."""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp

from equireduce.conditions import (
    domain_conditions,
    intrinsic_conditions,
    normalize_conditions,
    validate_condition,
)
from equireduce.errors import (
    InvalidSystemError,
    UnsupportedDomainError,
    UnsupportedExpressionError,
)


@dataclass(frozen=True)
class System:
    """A snapshot of ordered residuals and their original real domain."""

    residuals: tuple[sp.Expr, ...]
    unknowns: tuple[sp.Symbol, ...]
    parameters: tuple[sp.Symbol, ...] = ()
    conditions: tuple[sp.Basic, ...] = ()
    residual_names: tuple[str, ...] = ()

    @property
    def domain(self) -> str:
        return "algebraic"

    def __post_init__(self) -> None:
        for name in (
            "residuals",
            "unknowns",
            "parameters",
            "conditions",
            "residual_names",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        variables = self.unknowns + self.parameters
        if len(set(variables)) != len(variables):
            raise InvalidSystemError(
                "unknowns and parameters must be unique and disjoint"
            )
        if any(
            not isinstance(v, sp.Symbol) or v.is_real is not True for v in variables
        ):
            raise InvalidSystemError("declare real Symbol unknowns and parameters")
        rows = []
        for index, expression in enumerate(self.residuals):
            if isinstance(expression, (int, float)) and not isinstance(
                expression, bool
            ):
                expression = sp.sympify(expression)
            if not isinstance(expression, sp.Expr):
                raise InvalidSystemError(
                    f"residual {index}: expected a scalar SymPy Expr"
                )
            if expression.has(sp.Derivative):
                raise UnsupportedDomainError(
                    f"residual {index}: Derivative needs DAE API"
                )
            if expression.has(sp.Float, sp.nan, sp.zoo, sp.oo, -sp.oo):
                raise InvalidSystemError(
                    f"residual {index}: exact finite numbers required"
                )
            if expression.is_real is False:
                raise InvalidSystemError(f"residual {index}: complex expression")
            if expression.has(sp.Piecewise, sp.Integral, sp.Sum, sp.Product):
                raise UnsupportedExpressionError(
                    f"residual {index}: unsupported expression"
                )
            if not expression.free_symbols <= set(variables):
                raise InvalidSystemError(f"residual {index}: undeclared free symbols")
            rows.append(expression)
        for condition in self.conditions:
            if not validate_condition(condition):
                raise InvalidSystemError("conditions must be Boolean SymPy predicates")
            if isinstance(condition, sp.Basic):
                if not condition.free_symbols <= set(variables):
                    raise InvalidSystemError("condition contains undeclared symbols")
                if condition.has(sp.Float, sp.Derivative, sp.nan, sp.zoo):
                    raise InvalidSystemError("condition must be exact and algebraic")
        intrinsic = intrinsic_conditions(variables, (*rows, *self.conditions))
        guards = (*domain_conditions((*rows, *self.conditions)), *intrinsic)
        object.__setattr__(self, "residuals", tuple(rows))
        object.__setattr__(
            self, "conditions", normalize_conditions((*self.conditions, *guards))
        )
        names = self.residual_names or tuple(f"F{i}" for i in range(len(rows)))
        if len(names) != len(rows) or any(not isinstance(name, str) for name in names):
            raise InvalidSystemError("residual_names must match the residuals")
        object.__setattr__(self, "residual_names", names)

    @classmethod
    def algebraic(
        cls,
        residuals=(),
        unknowns=(),
        *,
        parameters=(),
        conditions=(),
        residual_names=(),
        float_policy="reject",
    ) -> System:
        """Construct an exact system, optionally rationalizing decimal inputs."""
        if float_policy not in ("reject", "exact_decimal"):
            raise InvalidSystemError("unknown float_policy")
        rows = tuple(residuals)
        conditions = tuple(conditions)
        if float_policy == "exact_decimal":

            def rationalize(expression):
                if isinstance(expression, float):
                    return sp.Rational(str(expression))
                if isinstance(expression, sp.Basic):
                    return expression.xreplace(
                        {
                            number: sp.Rational(str(number))
                            for number in expression.atoms(sp.Float)
                        }
                    )
                return expression

            rows = tuple(map(rationalize, rows))
            conditions = tuple(map(rationalize, conditions))
        return cls(
            rows, tuple(unknowns), tuple(parameters), conditions, tuple(residual_names)
        )
