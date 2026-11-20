from dataclasses import replace

import pytest
import sympy as sp

from equireduce import (
    LeanConfig,
    ReductionOptions,
    System,
    reduce_system,
    verify_certificate,
)
from equireduce.conditions import symbolic_zero_status

x, y, z, a, b = sp.symbols("x y z a b", real=True)


def test_first_vertical_slice_preserves_input_and_reconstructs_y():
    system = System.algebraic(
        (a * y - x, y + x - 1), (x, y), parameters=(a,), conditions=(sp.Ne(a, 0),)
    )
    result = reduce_system(system, candidates=(y,))
    assert result.source is system
    assert result.remaining_unknowns == (x,)
    assert result.reconstruction[y] == x / a
    assert sp.cancel(result.reduced_system.residuals[0] - (x / a + x - 1)) == 0
    assert result.coverage == "complete"
    assert result.additional_conditions == ()
    assert result.symbolic_check.status.value == "verified"
    assert result.formal_check.status.value == "not_requested"
    assert verify_certificate(system, result.certificate).status.value == "verified"


def test_pivot_guard_without_input_assumption_is_conditional():
    system = System.algebraic((a * y - b,), (y,), parameters=(a, b))
    result = reduce_system(system)
    assert result.reconstruction[y] == b / a
    assert sp.Ne(a, 0) in result.additional_conditions
    assert result.coverage == "conditional"


def test_known_zero_coefficient_does_not_discard_free_variable():
    system = System.algebraic((sp.S.Zero,), (y,))
    result = reduce_system(system)
    assert result.remaining_unknowns == (y,)
    assert dict(result.reconstruction) == {}


def test_pivot_conflicting_with_input_conditions_is_not_accepted():
    system = System.algebraic((x * y - 1,), (x, y), conditions=(sp.Eq(x, 0),))
    result = reduce_system(system, candidates=(y,))
    assert result.remaining_unknowns == (x, y)
    assert not result.reconstruction


def test_nonlinear_function_receives_exact_reconstruction_argument():
    f = sp.Function("f")
    system = System.algebraic((y - x**2, f(y) + x - a), (x, y), parameters=(a,))
    result = reduce_system(system, candidates=(y,))
    assert result.reconstruction[y] == x**2
    assert result.reduced_system.residuals == (f(x**2) + x - a,)


def test_conditions_and_reconstruction_follow_later_substitutions():
    system = System.algebraic((x * y - 1, x - a), (x, y), parameters=(a,))
    result = reduce_system(system, candidates=(y, x))
    assert result.reconstruction == {x: a, y: 1 / a}
    assert sp.Ne(a, 0) in result.conditions
    assert all(not guard.has(x, y) for guard in result.conditions)


def test_parameter_constraint_is_not_discarded_when_no_unknowns_remain():
    system = System.algebraic((x - a, 2 * x - b), (x,), parameters=(a, b))
    result = reduce_system(system)
    assert result.remaining_unknowns == ()
    assert result.reduced_system.residuals == (2 * a - b,)


def test_coupled_block_and_nonlinear_remainder():
    system = System.algebraic(
        (x + y - a, x - y - b, x**2 + y - z), (x, y, z), parameters=(a, b)
    )
    result = reduce_system(system, candidates=(x, y))
    assert result.remaining_unknowns == (z,)
    assert sp.cancel(result.reconstruction[x] - (a + b) / 2) == 0
    assert sp.cancel(result.reconstruction[y] - (a - b) / 2) == 0
    assert result.symbolic_check.status.value == "verified"


def test_original_denominator_guard_survives_reconstruction():
    system = System.algebraic((y - 1 / x, x - a), (x, y), parameters=(a,))
    result = reduce_system(system)
    assert sp.Ne(a, 0) in result.conditions
    assert result.coverage == "complete"


def test_certificate_cannot_be_reused_for_another_input():
    source = System.algebraic((y - x,), (x, y))
    certificate = reduce_system(source, candidates=(y,)).certificate
    other = System.algebraic((y - x - 1,), (x, y))
    assert verify_certificate(other, certificate).status.value == "failed"


def test_tampered_reconstruction_is_rejected():
    source = System.algebraic((y - x,), (x, y))
    result = reduce_system(source, candidates=(y,))
    forged = replace(
        result.certificate,
        reduction=replace(result.certificate.reduction, reconstruction=((y, x + 1),)),
    )
    assert verify_certificate(source, forged).status.value == "failed"


def test_tampered_pivot_claiming_nonlinear_coefficient_is_rejected():
    source = System.algebraic((y - x,), (x, y))
    result = reduce_system(source, candidates=(y,))
    core = result.certificate.reduction
    step = replace(core.steps[0], coefficient=y, remainder=y - x - y**2)
    forged = replace(result.certificate, reduction=replace(core, steps=(step,)))
    assert verify_certificate(source, forged).status.value == "failed"


def test_symbolic_zero_is_tristate_and_not_pointwise_nonzero():
    f = sp.Function("f")
    assert symbolic_zero_status(x - x).value == "zero"
    assert symbolic_zero_status(x).value == "not_identically_zero"
    assert symbolic_zero_status(f(x)).value == "unknown"


def test_reconstruction_mapping_is_immutable():
    result = reduce_system(System.algebraic((y - x,), (x, y)), candidates=(y,))
    with pytest.raises(TypeError):
        result.reconstruction[y] = 0


@pytest.mark.parametrize("budget", [True, 1.5, 0, -1])
def test_candidate_budget_requires_a_positive_integer(budget):
    with pytest.raises(ValueError):
        ReductionOptions(max_candidates=budget)


def test_command_is_an_argument_sequence_not_shell_text():
    with pytest.raises(ValueError):
        LeanConfig("lean", command="lake env lean")


def test_positive_unknown_cannot_be_reconstructed_as_negative():
    positive = sp.Symbol("p", positive=True)
    result = reduce_system(System.algebraic((positive + 1,), (positive,)))
    assert not result.reconstruction


def test_positive_domain_is_transported_to_reconstruction_parameters():
    positive = sp.Symbol("p", positive=True)
    result = reduce_system(
        System.algebraic((positive - a,), (positive,), parameters=(a,))
    )
    assert (a > 0) in result.conditions
    assert result.coverage == "complete"
