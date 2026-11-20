from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    InvalidSystemError,
    LeanConfig,
    TimeAffineTransform,
    reduce_implicit_in_coordinates,
    verify_implicit_coordinate_certificate,
    verify_time_transform,
)

t, a = sp.symbols("t a", real=True)
x, y, u, v = (sp.Function(n, real=True)(t) for n in ("x", "y", "u", "v"))
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def source():
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x, y),
        algebraic=(),
        residuals=(sp.diff(x, t) + y, sp.diff(y, t) - x),
        parameters=(a,),
        interval=(-1, 1),
    )


def chart():
    return TimeAffineTransform.create(
        source(), variables=(u, v), matrix=((1, t), (0, 1)), offset=(t**2, 0)
    )


def test_time_dependent_chart_includes_matrix_and_offset_derivatives():
    transform = chart()
    assert dict(transform.forward_map) == {x: u + t * v + t**2, y: v}
    assert (
        sp.expand(
            dict(transform.rate_map)[sp.diff(x, t)]
            - (sp.diff(u, t) + t * sp.diff(v, t) + v + 2 * t)
        )
        == 0
    )
    assert verify_time_transform(transform.source, transform).status.value == "verified"
    result = reduce_implicit_in_coordinates(
        transform.source, transform, differential=(u, v), algebraic=()
    )
    assert result.source == transform.source
    assert result.remaining_unknowns == (u, v)
    assert result.reconstruction == dict(transform.forward_map)
    assert (
        sp.expand(
            result.reduced_system.residuals[0]
            - (sp.diff(u, t) + t * sp.diff(v, t) + 2 * v + 2 * t)
        )
        == 0
    )
    assert (
        verify_implicit_coordinate_certificate(
            result.source, result.certificate
        ).status.value
        == "verified"
    )


def test_parameter_invertibility_is_an_explicit_interval_condition():
    s = source()
    transform = TimeAffineTransform.create(s, variables=(u, v), matrix=((a, 0), (0, 1)))
    result = reduce_implicit_in_coordinates(
        s, transform, differential=(u, v), algebraic=()
    )
    assert result.coverage == "conditional"
    assert sp.Ne(a, 0) in result.conditions


@pytest.mark.lean
def test_rational_time_scale_and_offset_have_a_kernel_checked_inverse_derivative():
    transform = TimeAffineTransform.create(
        replace(source(), interval=(sp.S.One, sp.Integer(2))),
        variables=(u, v),
        matrix=((t, 0), (0, 1)),
        offset=(1 / t, 0),
    )
    result = reduce_implicit_in_coordinates(
        transform.source,
        transform,
        differential=(u, v),
        algebraic=(),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified"
    assert sp.Ne(t, 0) in result.conditions
    assert (
        sp.cancel(
            dict(transform.rate_map)[sp.diff(x, t)] - (t * sp.diff(u, t) + u - 1 / t**2)
        )
        == 0
    )


def test_corrupt_inverse_or_rate_map_fails_verification():
    transform = chart()
    bad = replace(
        transform, rate_map=((sp.diff(x, t), sp.S.Zero), (sp.diff(y, t), sp.S.Zero))
    )
    assert verify_time_transform(transform.source, bad).status.value == "failed"
    bad = replace(transform, inverse_matrix=sp.ImmutableMatrix.eye(2))
    assert verify_time_transform(transform.source, bad).status.value == "failed"


@pytest.mark.parametrize(
    "matrix", [((1, 1), (1, 1)), ((x, 0), (0, 1)), ((sp.Float("1.1"), 0), (0, 1))]
)
def test_invalid_time_charts_are_rejected(matrix):
    with pytest.raises(InvalidSystemError):
        TimeAffineTransform.create(source(), variables=(u, v), matrix=matrix)


def test_initial_values_are_transported_exactly_without_changing_supplied_data():
    transform = chart()
    result = reduce_implicit_in_coordinates(
        transform.source,
        transform,
        differential=(u, v),
        algebraic=(),
        initial_time=0,
        initial_values={x: 2, y: 3},
    )
    assert result.initial_check.status == "verified"
    assert dict(result.initial_check.values)[u] == 2
    assert dict(result.initial_check.values)[v] == 3
    quotient = sp.Mul(a, sp.Pow(a, -1, evaluate=False), evaluate=False)
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_in_coordinates(
            transform.source,
            transform,
            differential=(u, v),
            algebraic=(),
            initial_time=0,
            initial_values={x: quotient, y: 0},
            parameter_values={a: 0},
        )


def test_coordinate_initial_time_is_never_parsed_from_a_string(monkeypatch):
    original = sp.sympify

    def forbidden(value, *args, **kwargs):
        if isinstance(value, str) and value == "user_time":
            raise AssertionError("user strings must never reach sympify")
        return original(value, *args, **kwargs)

    monkeypatch.setattr(sp, "sympify", forbidden)
    transform = chart()
    with pytest.raises(InvalidSystemError):
        reduce_implicit_in_coordinates(
            transform.source,
            transform,
            differential=(u, v),
            algebraic=(),
            initial_time="user_time",
            initial_values={x: 2, y: 3},
        )


def test_conflicting_supplied_coordinate_values_are_never_overwritten():
    transform = chart()
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_implicit_in_coordinates(
            transform.source,
            transform,
            differential=(u, v),
            algebraic=(),
            initial_time=0,
            initial_values={x: 2, y: 3, u: 99, v: 3},
        )


@pytest.mark.lean
def test_time_chart_composes_with_nonlinear_algebraic_elimination():
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(sp.diff(x, t) + sp.diff(y, t) + y, y - x**2),
        interval=(-1, 1),
    )
    transform = TimeAffineTransform.create(
        s,
        variables=(u, v),
        matrix=((1, 0), (t, 1)),
    )
    result = reduce_implicit_in_coordinates(
        s,
        transform,
        differential=(u,),
        algebraic=(v,),
        proof="require",
        lean=LeanConfig(str(PROJECT), timeout_seconds=180),
    )
    assert result.formal_check.status.value == "verified"
    assert result.reconstruction == {x: u, y: u**2}
    assert (
        sp.cancel(
            result.reduced_system.residuals[0] - ((1 + 2 * u) * sp.diff(u, t) + u**2)
        )
        == 0
    )


@pytest.mark.lean
def test_kernel_rejects_a_changed_coordinate_reconstruction():
    from equireduce.lean import compile_source, generate_lean

    transform = chart()
    result = reduce_implicit_in_coordinates(
        transform.source,
        transform,
        differential=(u, v),
        algebraic=(),
    )
    prefix, theorem = generate_lean(result.source, result.certificate).split(
        "theorem reduction_equivalence ", 1
    )
    statement, body = theorem.split(" := by", 1)
    assert "^ 2" in statement
    broken = (
        prefix
        + "theorem reduction_equivalence "
        + statement.replace("^ 2", "^ 3")
        + " := by"
        + body
    )
    assert (
        compile_source(broken, config=LeanConfig(str(PROJECT))).status.value == "failed"
    )


@pytest.mark.lean
@pytest.mark.parametrize("time_dependent", [False, True])
def test_kernel_checks_coordinate_trajectory_existence_and_full_composition(
    time_dependent,
):
    transform = (
        chart()
        if time_dependent
        else TimeAffineTransform.create(
            source(), variables=(u, v), matrix=((a, 0), (0, 1))
        )
    )
    result = reduce_implicit_in_coordinates(
        transform.source,
        transform,
        differential=(u, v),
        algebraic=(),
        proof="require",
        lean=LeanConfig(str(PROJECT), timeout_seconds=180),
    )
    assert result.formal_check.status.value == "verified"
    assert "∃" in result.formal_check.source
    assert "augmented_trajectory_equivalence" in result.formal_check.source
