from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    InvalidSystemError,
    LeanConfig,
    TimeAffineTransform,
    UnsupportedDomainError,
    reduce_implicit_dae,
    reduce_implicit_in_coordinates,
    search_implicit_partitions,
    verify_implicit_certificate,
)
from equireduce.lean import compile_source, generate_lean

t = sp.Symbol("t", real=True)
x, y, u, w, q, r = (
    sp.Function(n, real=True)(t) for n in ("x", "y", "u", "w", "q", "r")
)
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def source(case="nonlinear"):
    graph = x * u**2
    dynamic = sp.diff(x, t) + sp.diff(y, t) + y
    inputs = (u,)
    if case == "rational":
        graph = t * x * u**2 / w
        dynamic -= sp.diff(u, t)
        inputs = (u, w)
    elif case == "forcing":
        graph = x**2
        dynamic -= u + sp.diff(u, t)
    elif case == "charge":
        graph = x * u
        dynamic = sp.Derivative(x * u + y**2, t, evaluate=False) + y
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(dynamic, y - graph),
        inputs=inputs,
        interval=(-1, 1),
    )


def test_input_reconstruction_has_the_complete_chain_rule_and_domains(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("numeric probing is forbidden")

    monkeypatch.setattr(sp, "nsolve", forbidden)
    monkeypatch.setattr(sp.Expr, "equals", forbidden)
    monkeypatch.setattr(sp.MatrixBase, "rank", forbidden)
    s = source("rational")
    result = reduce_implicit_dae(s)
    assert result.reconstruction[y] == t * x * u**2 / w
    expected = (
        x * u**2 / w
        + t * u**2 * sp.diff(x, t) / w
        + 2 * t * x * u * sp.diff(u, t) / w
        - t * x * u**2 * sp.diff(w, t) / w**2
    )
    assert sp.cancel(result.reconstruction_derivatives[sp.diff(y, t)] - expected) == 0
    assert result.required_input_rates == (sp.diff(u, t), sp.diff(w, t))
    assert s.input_regularity == (
        (u, "differentiable_on_open_interval"),
        (w, "differentiable_on_open_interval"),
    )
    assert not s.parameters
    assert sp.Ne(w, 0) in result.conditions
    assert verify_implicit_certificate(s, result.certificate).status.value == "verified"
    generated = reduce_implicit_dae(s, proof="generate")
    assert generated.formal_check.status.value == "generated"
    broken = replace(
        result.certificate,
        reconstruction_derivatives=(
            (sp.diff(y, t), expected - 2 * t * x * u * sp.diff(u, t) / w),
        ),
    )
    assert verify_implicit_certificate(s, broken).status.value == "failed"


def test_exact_input_initial_values_and_rates_are_prescribed_and_checked():
    options = dict(
        initial_time=0,
        initial_values={x: 2},
        initial_input_values={u: 3},
        initial_input_rates={sp.diff(u, t): 5},
        initial_rates={
            sp.diff(x, t): sp.Rational(-39, 5),
            sp.diff(y, t): sp.Rational(-51, 5),
        },
    )
    result = reduce_implicit_dae(source(), **options)
    assert result.initial_check.status == "verified"
    assert dict(result.initial_check.values)[y] == 18
    assert dict(result.initial_check.input_values) == {u: 3}
    assert dict(result.initial_check.input_rates) == {sp.diff(u, t): 5}
    assert not result.initial_check.input_unknowns
    options["initial_rates"][sp.diff(y, t)] = 0
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(source(), **options)


def test_missing_input_samples_are_explicit_and_not_existential_state_rates():
    result = reduce_implicit_dae(
        source(),
        initial_time=0,
        initial_values={x: 2, y: 18},
        initial_input_values={u: 3},
    )
    check = result.initial_check
    assert check.status == "conditional"
    assert check.input_unknowns
    assert set(check.input_unknowns).isdisjoint(check.rate_unknowns)
    assert dict(check.input_rates)[sp.diff(u, t)] in check.input_unknowns
    assert dict(check.rate_witness)[sp.diff(x, t)].has(*check.input_unknowns)
    missing_values = reduce_implicit_dae(
        source(), initial_time=0, initial_values={x: 2, y: 18}
    )
    assert missing_values.initial_check.status == "conditional"
    assert missing_values.initial_check.obligations


@pytest.mark.parametrize(
    "bad",
    [
        {"initial_input_values": {w: 1}},
        {"initial_input_rates": {u: 1}},
        {"initial_input_values": {u: 0.5}},
        {"initial_input_rates": {sp.diff(u, t): "1"}},
    ],
)
def test_input_initial_validation_is_exact_and_declared(bad):
    with pytest.raises(InvalidSystemError):
        reduce_implicit_dae(source(), initial_time=0, initial_values={x: 0}, **bad)


def test_search_and_time_charts_transport_input_initial_samples():
    opts = dict(
        initial_time=0,
        initial_values={x: 2},
        initial_input_values={u: 3},
        initial_input_rates={sp.diff(u, t): 5},
    )
    result = search_implicit_partitions(source(), preferred_differential=(x,), **opts)
    assert result.initial_check.status == "verified"
    chart = TimeAffineTransform.create(
        source(), variables=(q, r), matrix=((1, 0), (t, 1))
    )
    opts["initial_values"] = {x: 2, y: 18}
    mapped = reduce_implicit_in_coordinates(
        source(), chart, differential=(q,), algebraic=(r,), **opts
    )
    assert mapped.initial_check.status == "verified"
    assert mapped.required_input_rates == (sp.diff(u, t),)


def test_reconstruction_from_input_rates_is_not_allowed_to_introduce_second_rates():
    s = replace(source(), residuals=(sp.diff(x, t) + y, y - sp.diff(u, t)))
    with pytest.raises(UnsupportedDomainError):
        reduce_implicit_dae(s)
    with pytest.raises(UnsupportedDomainError):
        replace(source(), regularity="continuous_on_open_interval")


def test_input_rate_domain_is_checked_before_point_substitution():
    s = replace(source(), residuals=(sp.diff(x, t) + y / sp.diff(u, t), y - x * u))
    result = reduce_implicit_dae(s)
    assert sp.Ne(sp.diff(u, t), 0) in result.conditions
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_dae(
            s,
            initial_time=0,
            initial_values={x: 1},
            initial_input_values={u: 1},
            initial_input_rates={sp.diff(u, t): 0},
        )


@pytest.mark.lean
def test_input_can_drive_a_system_with_no_retained_state():
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(y,),
        differential=(),
        algebraic=(y,),
        residuals=(y - u,),
        inputs=(u,),
        interval=(-1, 1),
    )
    result = reduce_implicit_dae(s, proof="require", lean=LeanConfig(str(PROJECT)))
    assert not result.remaining_unknowns
    assert result.reconstruction_derivatives[sp.diff(y, t)] == sp.diff(u, t)
    assert result.formal_check.status.value == "verified"


@pytest.mark.lean
@pytest.mark.parametrize("case", ["forcing", "nonlinear", "rational", "charge"])
def test_real_kernel_checks_input_regularity_and_actual_input_derivatives(case):
    result = reduce_implicit_dae(
        source(case), proof="require", lean=LeanConfig(str(PROJECT))
    )
    assert result.formal_check.status.value == "verified"
    assert "hInputRegularity" in result.formal_check.source
    assert "deriv" in result.formal_check.source


@pytest.mark.lean
def test_time_chart_composes_with_external_input_trajectory_proof():
    s = source()
    chart = TimeAffineTransform.create(
        s, variables=(q, r), matrix=((1, t), (0, 1)), offset=(t**2, 0)
    )
    result = reduce_implicit_in_coordinates(
        s,
        chart,
        differential=(q, r),
        algebraic=(),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified"
    assert "hInputRegularity" in result.formal_check.source


@pytest.mark.lean
def test_kernel_rejects_zeroing_the_input_rate_in_the_reduced_equation():
    result = reduce_implicit_dae(source())
    prefix, theorem = generate_lean(result.source, result.certificate).split(
        "theorem reduction_equivalence ", 1
    )
    statement, body = theorem.split(" := by", 1)
    left, right = statement.split(" ↔", 1)
    rate = "(deriv er_trajectory_2 er_time)"
    assert rate in right
    broken = (
        prefix
        + "theorem reduction_equivalence "
        + left
        + " ↔"
        + right.replace(rate, "0")
        + " := by"
        + body
    )
    assert (
        compile_source(broken, config=LeanConfig(str(PROJECT))).status.value == "failed"
    )
