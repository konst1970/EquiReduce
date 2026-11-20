from dataclasses import FrozenInstanceError

import pytest
import sympy as sp

from equireduce import ImplicitDAESystem, InvalidSystemError, UnsupportedDomainError

t, R, C = sp.symbols("t R C", real=True)
x, y, u = (sp.Function(name, real=True)(t) for name in ("x", "y", "u"))


def make_system(**overrides):
    arguments = dict(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(C * sp.diff(x, t) + y, y - x**2),
        parameters=(R, C),
        interval=(-1, 1),
        residual_names=("dynamic", "constraint"),
    )
    arguments.update(overrides)
    return ImplicitDAESystem.create(**arguments)


def test_implicit_contract_preserves_order_rates_and_a_singular_mass_case():
    source = make_system()
    assert source.unknowns == (x, y)
    assert source.residuals[0].has(sp.Derivative)
    assert source.regularity == "differentiable_on_open_interval"
    assert source.domain == "time"
    assert source.interval_condition is sp.true
    assert sp.Ne(C, 0) not in source.conditions
    assert make_system(residuals=(y, y - x**2)).residuals[0] == y
    with pytest.raises(FrozenInstanceError):
        source.time = R


def test_input_functions_are_declared_separately_from_constant_parameters():
    source = make_system(inputs=(u,), residuals=(C * sp.diff(x, t) - u, y - x))
    assert source.inputs == (u,)
    assert t not in source.parameters
    assert source.residuals[0].has(u)
    with pytest.raises(InvalidSystemError, match="input"):
        make_system(residuals=(sp.diff(x, t) - u, y - x))


def test_domains_are_captured_before_any_state_or_rate_substitution():
    quotient = sp.Mul(y, sp.Pow(y, -1, evaluate=False), evaluate=False)
    source = make_system(
        residuals=(sp.Add(sp.diff(x, t), quotient, evaluate=False), y - x)
    )
    assert sp.Ne(y, 0) in source.conditions
    rate = sp.diff(x, t)
    quotient = sp.Mul(rate, sp.Pow(rate, -1, evaluate=False), evaluate=False)
    assert sp.Ne(rate, 0) in make_system(residuals=(quotient, y - x)).conditions


@pytest.mark.parametrize(
    "overrides",
    [
        {"residuals": ("x", y - x)},
        {"residuals": (sp.Float("0.1") * sp.diff(x, t), y - x)},
        {"parameters": (t, C)},
        {"unknowns": (x, x)},
        {"algebraic": (x,)},
        {"differential": ()},
        {"interval": ("-1", 1)},
        {"interval": (1, 0)},
        {"residual_names": ("one",)},
    ],
)
def test_invalid_contract_inputs_are_rejected(overrides):
    with pytest.raises(InvalidSystemError):
        make_system(**overrides)


@pytest.mark.parametrize(
    "expression",
    [
        sp.diff(x, t, 2),
        sp.Derivative(x, R, evaluate=False),
        sp.Piecewise((x, x > 0), (-x, True)),
        sp.DiracDelta(t),
    ],
)
def test_unsupported_differential_or_nonsmooth_forms_are_explicit(expression):
    with pytest.raises(UnsupportedDomainError):
        make_system(residuals=(expression, y - x))


def test_rational_composite_derivative_is_retained_in_original_snapshot():
    original = sp.Derivative(x**2 + t * x, t, evaluate=False)
    source = make_system(residuals=(original + y, y - x))
    assert source.residuals[0].has(original)


def test_sign_assumptions_are_preserved_as_pointwise_conditions():
    positive = sp.Function("positive", positive=True)(t)
    source = make_system(
        unknowns=(x, positive),
        algebraic=(positive,),
        residuals=(sp.diff(x, t) + positive, positive - x),
    )
    assert sp.Gt(positive, 0, evaluate=False) in source.conditions
