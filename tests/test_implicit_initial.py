import pytest
import sympy as sp

from equireduce import ImplicitDAESystem, InvalidSystemError, reduce_implicit_dae

t, C, a = sp.symbols("t C a", real=True)
x, y = (sp.Function(n, real=True)(t) for n in ("x", "y"))


def source(coefficient=sp.S.One):
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(coefficient * sp.diff(x, t) + y, y - x**2),
        interval=(-1, 1),
        parameters=(C,),
    )


def test_exact_initial_data_and_missing_algebraic_values_are_reconstructed():
    result = reduce_implicit_dae(source(), initial_time=0, initial_values={x: 2})
    check = result.initial_check
    assert check.status == "verified"
    assert dict(check.values) == {x: 2, y: 4}
    assert dict(check.derived_values) == {y: 4}
    assert dict(check.rate_witness)[sp.diff(x, t)] == -4
    assert check.scope == "pointwise_residuals_and_reconstruction"
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(source(), initial_time=0, initial_values={x: 2, y: 3})


def test_symbolic_initial_constraints_remain_explicit_obligations():
    result = reduce_implicit_dae(source(), initial_time=0, initial_values={x: a, y: 4})
    assert result.initial_check.status == "conditional"
    assert any(
        isinstance(v, sp.Equality) and sp.cancel(v.lhs - v.rhs - (4 - a**2)) == 0
        for v in result.initial_check.obligations
    )


def test_degenerate_mass_branches_are_not_replaced_by_a_nonzero_assumption():
    conditional = reduce_implicit_dae(
        source(C), initial_time=0, initial_values={x: 2, y: 4}
    )
    assert conditional.initial_check.status == "conditional"
    assert conditional.initial_check.rate_equations
    assert sp.Ne(C, 0) not in conditional.initial_check.obligations
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(
            source(C), initial_time=0, initial_values={x: 2}, parameter_values={C: 0}
        )
    good = reduce_implicit_dae(
        source(C), initial_time=0, initial_values={x: 0}, parameter_values={C: 0}
    )
    assert good.initial_check.status == "verified"


def test_supplied_algebraic_rate_is_checked_against_the_chain_rule():
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(
            source(),
            initial_time=0,
            initial_values={x: 2},
            initial_rates={sp.diff(x, t): -4, sp.diff(y, t): 0},
        )
    result = reduce_implicit_dae(
        source(),
        initial_time=0,
        initial_values={x: 2},
        initial_rates={sp.diff(x, t): -4, sp.diff(y, t): -16},
    )
    assert result.initial_check.status == "verified"


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(initial_time=1, initial_values={x: 2}),
        dict(initial_time=0, initial_values={x: sp.Float("2")}),
        dict(initial_time=0, initial_values={}),
        dict(initial_time=0),
    ],
)
def test_invalid_initial_inputs_are_rejected(kwargs):
    with pytest.raises(InvalidSystemError):
        reduce_implicit_dae(source(), **kwargs)


def test_initial_data_symbols_cannot_collide_with_internal_rate_unknowns():
    value = sp.Symbol("initial_rate_0", real=True)
    result = reduce_implicit_dae(source(), initial_time=0, initial_values={x: value})
    assert result.initial_check.status == "verified"
    assert dict(result.initial_check.rate_witness)[sp.diff(x, t)] == -(value**2)


def test_initial_time_parameter_substitution_is_exact():
    result = reduce_implicit_dae(
        source(), initial_time=C, initial_values={x: 2}, parameter_values={C: 0}
    )
    assert result.initial_check.time == 0


def test_partial_initial_expressions_keep_their_domains_before_cancellation():
    quotient = sp.Mul(a, sp.Pow(a, -1, evaluate=False), evaluate=False)
    result = reduce_implicit_dae(source(), initial_time=0, initial_values={x: quotient})
    assert result.initial_check.status == "conditional"
    assert sp.Ne(a, 0) in result.initial_check.obligations
    result = reduce_implicit_dae(
        source(),
        initial_time=0,
        initial_values={x: 0},
        parameter_values={C: 1 / a},
    )
    assert result.initial_check.status == "conditional"
    assert sp.Ne(a, 0) in result.initial_check.obligations


def test_cyclic_initial_parameter_assignments_are_rejected():
    with pytest.raises(InvalidSystemError, match="cyclic"):
        reduce_implicit_dae(
            source(), initial_time=0, initial_values={x: 2}, parameter_values={C: C + 1}
        )


def test_conflicting_exact_rate_equations_are_incompatible():
    from dataclasses import replace

    s = replace(
        source(),
        residuals=(sp.diff(x, t) - 1, sp.diff(x, t) - 2, y - x**2),
        residual_names=(),
    )
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(s, initial_time=0, initial_values={x: 0})


def test_missing_initial_input_data_has_explicit_placeholders():
    from dataclasses import replace

    u = sp.Function("u", real=True)(t)
    s = replace(
        source(), inputs=(u,), residuals=(sp.diff(x, t) - sp.diff(u, t), y - x**2)
    )
    result = reduce_implicit_dae(s, initial_time=0, initial_values={x: 0})
    assert result.initial_check.status == "conditional"
    assert result.initial_check.input_unknowns
    assert (
        dict(result.initial_check.input_rates)[sp.diff(u, t)]
        in result.initial_check.input_unknowns
    )
