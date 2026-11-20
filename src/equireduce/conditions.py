"""Exact domain predicates; unknown never means proven nonzero."""

from collections.abc import Iterable

import sympy as sp
from sympy.core.relational import Relational


def normalize_conditions(conditions: Iterable) -> tuple:
    """Normalize nonzero guards without dropping excluded singularities."""
    result = []
    for condition in conditions:
        if condition is True:
            continue
        if condition is False:
            condition = sp.false
        if isinstance(condition, sp.And):
            nested = normalize_conditions(condition.args)
        elif isinstance(condition, sp.Unequality):
            expression = sp.factor(condition.lhs - condition.rhs)
            if isinstance(expression, sp.Pow) and expression.exp.is_integer:
                expression = expression.base
            _, expression = expression.as_coeff_Mul()
            nested = (sp.Ne(expression, 0, evaluate=expression.is_number is True),)
        else:
            nested = (condition,)
        for item in nested:
            if item is not sp.true and item not in result:
                result.append(item)
    return tuple(result)


def domain_conditions(expressions: Iterable) -> tuple:
    """Read partial-operation domains before cancellation or elimination."""
    guards = []
    for expression in expressions:
        for node in sp.preorder_traversal(expression):
            if isinstance(node, sp.Pow):
                exponent = node.exp
                if exponent.is_negative:
                    guards.append(sp.Ne(node.base, 0))
                if isinstance(exponent, sp.Rational) and exponent.q % 2 == 0:
                    guards.append(node.base > 0 if exponent < 0 else node.base >= 0)
            elif node.func is sp.log:
                guards.append(node.args[0] > 0)
    return normalize_conditions(guards)


def assumption_consistency(conditions: Iterable) -> str:
    """Conservatively detect contradictions; do not claim nonlinear feasibility."""
    conditions = tuple(simplify_condition(v) for v in conditions)
    combined = sp.And(*conditions)
    if combined is sp.false:
        return "inconsistent"
    if combined is sp.true:
        return "consistent"
    return "unknown"


def simplify_condition(condition):
    """Use exact arithmetic/Boolean rules, never Relational.simplify/equals.

    General inequality feasibility is deliberately left unresolved. Explicit
    symbolic domains are preserved even when Symbol assumptions imply them.
    """
    if isinstance(condition, (sp.And, sp.Or, sp.Not)):
        return condition.func(*(simplify_condition(v) for v in condition.args))
    if not isinstance(condition, Relational):
        return condition
    difference = sp.factor(sp.cancel(condition.lhs - condition.rhs))
    if difference.is_Rational:
        return condition.func(difference, sp.S.Zero)
    if isinstance(condition, (sp.Equality, sp.Unequality)):
        return condition.func(difference, sp.S.Zero, evaluate=False)
    return condition


def intrinsic_conditions(variables, expressions) -> tuple:
    """Make supported SymPy sign assumptions part of the explicit domain."""
    from equireduce.errors import InvalidSystemError

    atoms = list(variables)
    for expression in expressions:
        if isinstance(expression, sp.Basic):
            atoms.extend(
                sorted(expression.atoms(sp.core.function.AppliedUndef), key=sp.srepr)
            )
    guards = []
    allowed = {
        "real",
        "positive",
        "negative",
        "nonnegative",
        "nonpositive",
        "nonzero",
        "zero",
        "commutative",
        "finite",
        "complex",
        "extended_real",
        "hermitian",
        "imaginary",
        "infinite",
        "extended_positive",
        "extended_negative",
        "extended_nonnegative",
        "extended_nonpositive",
        "extended_nonzero",
    }
    for atom in dict.fromkeys(atoms):
        assumptions = (
            atom._assumptions_orig if isinstance(atom, sp.Symbol) else atom.func._kwargs
        )
        if set(assumptions) - allowed:
            raise InvalidSystemError("unsupported discrete or non-real assumption")
        for property_name, constructor in (
            ("positive", sp.Gt),
            ("negative", sp.Lt),
            ("nonnegative", sp.Ge),
            ("nonpositive", sp.Le),
            ("nonzero", sp.Ne),
            ("zero", sp.Eq),
        ):
            if getattr(atom, "is_" + property_name) is True:
                guards.append(constructor(atom, 0, evaluate=False))
    return tuple(dict.fromkeys(guards))


def validate_condition(condition) -> bool:
    return isinstance(condition, (Relational, sp.And, sp.Or, sp.Not)) or condition in (
        sp.true,
        sp.false,
        True,
        False,
    )


def symbolic_zero_status(expression):
    """Classify identities separately from pointwise nonvanishing."""
    from equireduce._core import symbolic_zero_status as classify

    return classify(expression)
