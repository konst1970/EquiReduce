from dataclasses import replace

import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    ProofVerificationError,
    UnsupportedDomainError,
    reduce_implicit_dae,
    verify_implicit_certificate,
)

t, a, C = sp.symbols("t a C", real=True)
x, y, z, u = (sp.Function(name, real=True)(t) for name in ("x", "y", "z", "u"))


def make_system(rows=None, **overrides):
    arguments = dict(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(C * sp.diff(x, t) + y, y - x**2) if rows is None else rows,
        interval=(-1, 1),
        parameters=(a, C),
        residual_names=(),
    )
    arguments.update(overrides)
    return ImplicitDAESystem.create(**arguments)


def test_implicit_reduction_does_not_divide_by_the_dynamic_coefficient():
    source = make_system()
    result = reduce_implicit_dae(source)
    assert result.source == source
    assert result.form == "implicit"
    assert result.remaining_unknowns == (x,)
    assert result.reconstruction == {y: x**2}
    assert result.reconstruction_derivatives == {sp.diff(y, t): 2 * x * sp.diff(x, t)}
    assert result.reduced_system.residuals == (C * sp.diff(x, t) + x**2,)
    assert result.residual_source_indices == (0,)
    assert result.coverage == "complete"
    assert sp.Ne(C, 0) not in result.conditions
    assert result.structure.rank.status == "conditional"
    assert result.index_status == "not_classified"
    assert result.formal_check.status.value == "not_requested"
    assert (
        verify_implicit_certificate(source, result.certificate).status.value
        == "verified"
    )
    with pytest.raises(TypeError):
        result.reconstruction[y] = x


def test_chain_rule_preserves_an_implicit_rate_equation_at_its_singular_points():
    result = reduce_implicit_dae(
        make_system((sp.diff(x, t) + sp.diff(y, t) + y, y - x**2))
    )
    assert (
        sp.expand(
            result.reduced_system.residuals[0] - ((1 + 2 * x) * sp.diff(x, t) + x**2)
        )
        == 0
    )
    assert result.coverage == "complete"
    assert not result.conditions


def test_original_algebraic_constraints_are_retained_and_not_called_index_one():
    source = make_system(
        (sp.diff(x, t) + y, y - x, x - a),
        residual_names=("dynamic", "pivot", "constraint"),
    )
    result = reduce_implicit_dae(source)
    assert result.reduced_system.residual_names == ("dynamic", "constraint")
    assert result.residual_source_indices == (0, 2)
    assert result.reduced_system.residuals[1] == x - a
    assert result.index_status == "not_classified"


@pytest.mark.parametrize("declared", [False, True])
def test_algebraic_pivot_guards_are_explicit_and_have_honest_coverage(declared):
    source = make_system(
        (C * sp.diff(x, t) + y, a * y - x),
        conditions=(sp.Ne(a, 0),) if declared else (),
    )
    result = reduce_implicit_dae(source)
    assert result.reconstruction == {y: x / a}
    assert sp.Ne(a, 0) in result.conditions
    assert result.coverage == ("complete" if declared else "conditional")
    assert sp.Ne(C, 0) not in result.conditions


def test_time_dependent_reconstruction_uses_its_partial_time_derivative():
    source = make_system((sp.diff(x, t) + sp.diff(y, t), t * y - x), interval=(0, 1))
    result = reduce_implicit_dae(source)
    assert result.reconstruction[y] == x / t
    assert (
        sp.simplify(
            result.reconstruction_derivatives[sp.diff(y, t)]
            - (sp.diff(x, t) / t - x / t**2)
        )
        == 0
    )
    assert sp.Ne(t, 0) in result.conditions


def test_a_coupled_algebraic_block_is_eliminated_exactly():
    source = make_system(
        (sp.diff(x, t) + y + z, 2 * y + z - x**2, y - z - t * x),
        unknowns=(x, y, z),
        algebraic=(y, z),
    )
    result = reduce_implicit_dae(source)
    assert result.remaining_unknowns == (x,)
    assert sp.expand(result.reconstruction[y] - (x**2 + t * x) / 3) == 0
    assert sp.expand(result.reconstruction[z] - (x**2 - 2 * t * x) / 3) == 0
    assert (
        verify_implicit_certificate(source, result.certificate).status.value
        == "verified"
    )


def test_original_pole_and_normalized_composite_derivative_both_survive():
    quotient = sp.Mul(y, sp.Pow(y, -1, evaluate=False), evaluate=False)
    original = sp.Add(sp.Derivative(x**2, t, evaluate=False), quotient, evaluate=False)
    source = make_system((original, y - x**2))
    result = reduce_implicit_dae(source)
    assert sp.Ne(x, 0) in result.conditions
    assert result.coverage == "complete"
    assert (
        sp.expand(result.reduced_system.residuals[0] - (2 * x * sp.diff(x, t) + 1)) == 0
    )


def test_rational_charge_can_cancel_rates_without_losing_its_original_domain():
    row = sp.Derivative(x / y, t, evaluate=False) + y
    source = make_system((row, y - t * x), interval=(0, 1))
    result = reduce_implicit_dae(source)
    assert sp.cancel(result.reduced_system.residuals[0] - (t * x - 1 / t**2)) == 0
    assert result.structure.rank.rank == 0
    assert result.remaining_unknowns == (x,)
    assert sp.Ne(t * x, 0) in result.conditions
    assert (
        verify_implicit_certificate(source, result.certificate).status.value
        == "verified"
    )


def test_degenerate_cases_with_one_empty_partition_are_valid():
    ode = make_system((sp.diff(x, t) + x,), unknowns=(x,), algebraic=())
    assert reduce_implicit_dae(ode).reduced_system.residuals == ode.residuals
    algebraic = make_system((y - a,), unknowns=(y,), differential=(), algebraic=(y,))
    result = reduce_implicit_dae(algebraic)
    assert result.remaining_unknowns == ()
    assert result.reduced_system.residuals == ()
    assert result.reconstruction_derivatives == {sp.diff(y, t): 0}


@pytest.mark.parametrize(
    "rows",
    [
        (sp.diff(x, t) ** 2 + y, y - x),
        (sp.diff(x, t) - y, x),
        (sp.diff(x, t) + y, y**2 - x),
    ],
)
def test_unsupported_rate_nonlinearity_high_index_or_nonlinear_elimination_is_explicit(
    rows,
):
    with pytest.raises(UnsupportedDomainError):
        reduce_implicit_dae(make_system(rows))


def test_external_forcing_and_input_dependent_reconstruction_are_preserved():
    source = make_system((sp.diff(x, t) + y - u, y - x), inputs=(u,))
    result = reduce_implicit_dae(source)
    assert result.reduced_system.residuals[0].has(u)
    result = reduce_implicit_dae(make_system((sp.diff(x, t) + y, y - u), inputs=(u,)))
    assert result.reconstruction[y] == u
    assert result.reconstruction_derivatives[sp.diff(y, t)] == sp.diff(u, t)


def test_tampered_residual_rate_domain_and_source_indices_fail_independent_replay():
    source = make_system((sp.diff(x, t) + sp.diff(y, t), a * y - x))
    result = reduce_implicit_dae(source)
    modifications = [
        dict(reconstruction=((y, sp.S.Zero),)),
        dict(reconstruction_derivatives=((sp.diff(y, t), sp.S.Zero),)),
        dict(reduced_residuals=(sp.S.Zero,)),
        dict(conditions=()),
        dict(residual_source_indices=()),
    ]
    for fields in modifications:
        forged = replace(result.certificate, **fields)
        assert verify_implicit_certificate(source, forged).status.value == "failed"


def test_unsupported_input_expression_is_not_reported_as_a_formal_success():
    source = make_system((C * sp.diff(x, t) + y - sp.sin(u), y - x**2), inputs=(u,))
    result = reduce_implicit_dae(source, proof="generate")
    assert result.formal_check.status.value == "unsupported"
    with pytest.raises(ProofVerificationError) as error:
        reduce_implicit_dae(source, proof="require")
    assert error.value.verification.status.value == "unsupported"
    assert error.value.candidate.reconstruction[y] == x**2


def test_generic_lean_runner_reports_an_unsupported_input_expression():
    from equireduce import verify_with_lean

    result = reduce_implicit_dae(
        make_system((C * sp.diff(x, t) + y - sp.sin(u), y - x**2), inputs=(u,))
    )
    checked = verify_with_lean(result.source, result.certificate, config=None)
    assert checked.status.value == "unsupported"
