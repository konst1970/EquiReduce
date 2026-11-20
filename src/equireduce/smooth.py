"""Declared differentiable scalar laws and exact first-order chain rules."""

from dataclasses import dataclass

import sympy as sp

from equireduce.errors import InvalidSystemError, UnsupportedDomainError


@dataclass(frozen=True)
class SmoothFunction:
    name: str
    arity: int

    def __post_init__(self):
        if not isinstance(self.name, str) or not self.name or len(self.name) > 128:
            raise InvalidSystemError("smooth law needs a bounded function name")
        if type(self.arity) is not int or self.arity not in (1, 2):
            raise UnsupportedDomainError(
                "smooth laws currently support one or two arguments"
            )

    @property
    def function(self):
        return sp.Function(self.name, real=True)

    @property
    def partials(self):
        return tuple(
            sp.Function(f"{self.name}__d{i}", real=True) for i in range(self.arity)
        )


def derivative(expression, rates, declarations=()):
    """Differentiate through declared laws; rates are independent jet values."""
    if expression in rates:
        return rates[expression]
    if not expression.has(*rates):
        return sp.S.Zero
    if isinstance(expression, sp.Add):
        return sp.Add(*(derivative(v, rates, declarations) for v in expression.args))
    if isinstance(expression, sp.Mul):
        return sum(
            derivative(v, rates, declarations)
            * sp.Mul(*(w for j, w in enumerate(expression.args) if j != i))
            for i, v in enumerate(expression.args)
        )
    if isinstance(expression, sp.Pow) and expression.exp.is_Integer:
        return (
            expression.exp
            * expression.base ** (expression.exp - 1)
            * derivative(expression.base, rates, declarations)
        )
    if expression.func is sp.exp:
        return expression * derivative(expression.args[0], rates, declarations)
    law = next((law for law in declarations if expression.func == law.function), None)
    if law is not None and len(expression.args) == law.arity:
        return sum(
            p(*expression.args) * derivative(v, rates, declarations)
            for p, v in zip(law.partials, expression.args, strict=True)
        )
    raise UnsupportedDomainError(f"unproved smooth derivative: {expression}")


def time_derivative(expression, source):
    return derivative(
        expression,
        {
            source.time: sp.S.One,
            **{
                v: sp.Derivative(v, source.time)
                for v in (*source.unknowns, *source.inputs)
            },
        },
        source.smooth_functions,
    )


def raw_replace(expression, mapping):
    if expression in mapping:
        return mapping[expression]
    if not expression.args:
        return expression
    args = tuple(raw_replace(v, mapping) for v in expression.args)
    if isinstance(expression, (sp.Add, sp.Mul, sp.Pow, sp.core.relational.Relational)):
        return expression.func(*args, evaluate=False)
    return expression.func(*args)


def branch_data(expressions, choices):
    """Select ordered Piecewise branches on explicit open regions."""
    nodes = set().union(*(v.atoms(sp.Piecewise) for v in expressions))
    choices = tuple(choices)
    if len({v for v, _ in choices}) != len(choices) or {v for v, _ in choices} != nodes:
        raise UnsupportedDomainError(
            "declare exactly one branch for every Piecewise node"
        )
    mapping = {}
    guards = []
    for node, index in choices:
        if type(index) is not int or not 0 <= index < len(node.args):
            raise InvalidSystemError("invalid Piecewise branch index")
        if node.args[-1].cond is not sp.true:
            raise UnsupportedDomainError("Piecewise must have a total default branch")
        for j, (_, condition) in enumerate(node.args[: index + 1]):
            if condition is sp.true:
                continue
            active = condition if j == index else sp.Not(condition)
            if isinstance(active, sp.LessThan):
                active = sp.Lt(active.lhs, active.rhs, evaluate=False)
            elif isinstance(active, sp.GreaterThan):
                active = sp.Gt(active.lhs, active.rhs, evaluate=False)
            if not isinstance(active, (sp.StrictLessThan, sp.StrictGreaterThan)):
                raise UnsupportedDomainError(
                    "smooth branches require strict inequality regions"
                )
            guards.append(active)
        mapping[node] = node.args[index].expr
    # Inner choices must be applied to selected outer bodies as well.
    for _ in range(len(mapping)):
        mapping = {
            k: raw_replace(v, {a: b for a, b in mapping.items() if a != k})
            for k, v in mapping.items()
        }
    return mapping, tuple(guards)
