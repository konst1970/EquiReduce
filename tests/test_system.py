from dataclasses import FrozenInstanceError

import pytest
import sympy as sp

from equireduce import InvalidSystemError, System, UnsupportedDomainError

x, y, a = sp.symbols("x y a", real=True)


def test_system_snapshots_mutable_input_and_retains_order():
    rows = [a * y - x, x + y - 1]
    system = System.algebraic(rows, (x, y), parameters=(a,))
    rows.clear()
    assert system.residuals == (a * y - x, x + y - 1)
    assert system.unknowns == (x, y)
    assert system.parameters == (a,)
    with pytest.raises(FrozenInstanceError):
        system.unknowns = ()


@pytest.mark.parametrize(
    ("residuals", "unknowns", "parameters"),
    [
        ((x,), (x, x), ()),
        ((x + a,), (x,), ()),
        ((x,), (x,), (x,)),
        ((sp.Float("0.1") * x,), (x,), ()),
        (("x",), (x,), ()),
        ((sp.Eq(x, 0),), (x,), ()),
        ((sp.Symbol("z"),), (sp.Symbol("z"),), ()),
        ((sp.nan,), (), ()),
    ],
)
def test_invalid_system_is_rejected(residuals, unknowns, parameters):
    with pytest.raises(InvalidSystemError):
        System.algebraic(residuals, unknowns, parameters=parameters)


def test_derivative_is_rejected_explicitly():
    t = sp.Symbol("t", real=True)
    q = sp.Function("q")(t)
    with pytest.raises(UnsupportedDomainError, match="Derivative"):
        System.algebraic((sp.diff(q, t),), (), parameters=(t,))


def test_empty_and_overdetermined_systems_are_valid():
    assert System.algebraic((), (x,)).residuals == ()
    assert len(System.algebraic((x, 2 * x, x - 1), (x,)).residuals) == 3


def test_input_domain_is_retained_before_cancellation():
    expression = sp.Mul(x - 1, sp.Pow(x - 1, -1, evaluate=False), evaluate=False)
    system = System.algebraic((expression,), (x,))
    assert sp.Ne(x - 1, 0) in system.conditions


def test_logarithm_and_even_root_domains_are_preserved():
    system = System.algebraic((sp.log(x) + sp.sqrt(y),), (x, y))
    assert (x > 0) in system.conditions
    assert (y >= 0) in system.conditions


def test_decimal_conversion_requires_explicit_consent():
    system = System.algebraic(
        (sp.Float("0.1") * x,), (x,), float_policy="exact_decimal"
    )
    assert system.residuals == (x / 10,)


def test_matrix_input_is_snapshotted():
    matrix = sp.Matrix([x, y])
    system = System.algebraic(matrix, (x, y))
    matrix[0] = 99
    assert system.residuals == (x, y)


def test_discrete_symbol_domains_are_not_silently_relaxed_to_reals():
    integer = sp.Symbol("n", integer=True)
    with pytest.raises(InvalidSystemError, match="assumption"):
        System.algebraic((integer - 1,), (integer,))
