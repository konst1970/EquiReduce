from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    LeanConfig,
    SmoothFunction,
    reduce_implicit_dae,
    verify_implicit_certificate,
)
from equireduce.lean import compile_source, generate_lean

t = sp.Symbol("t", real=True)
x, z, y = (sp.Function(n, real=True)(t) for n in ("x", "z", "y"))
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def structural():
    q = SmoothFunction("Qbe", 2)
    charge = q.function(x, z)
    source = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, z, y),
        differential=(x, z),
        algebraic=(y,),
        residuals=(
            sp.Derivative(charge, t, evaluate=False) + y,
            sp.diff(z, t) - x,
            y - charge,
        ),
        interval=(-1, 1),
        smooth_functions=(q,),
    )
    return source, q


def test_multivariable_charge_keeps_both_partial_derivatives(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("numerical methods are forbidden")

    monkeypatch.setattr(sp.Expr, "equals", forbidden)
    monkeypatch.setattr(sp, "nsolve", forbidden)
    source, q = structural()
    result = reduce_implicit_dae(source)
    expected = q.partials[0](x, z) * sp.diff(x, t) + q.partials[1](x, z) * sp.diff(z, t)
    assert sp.expand(result.reconstruction_derivatives[sp.diff(y, t)] - expected) == 0
    assert (
        sp.expand(result.reduced_system.residuals[0] - expected - q.function(x, z)) == 0
    )
    forged = replace(
        result.certificate,
        reconstruction_derivatives=(
            (sp.diff(y, t), expected - q.partials[1](x, z) * sp.diff(z, t)),
        ),
    )
    assert verify_implicit_certificate(source, forged).status.value == "failed"


def test_exponential_reconstruction_has_an_exact_chain_rule():
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(sp.diff(x, t) + sp.diff(y, t) + y, y - sp.exp(x)),
        interval=(-1, 1),
    )
    result = reduce_implicit_dae(s)
    assert result.reconstruction_derivatives[sp.diff(y, t)] == sp.exp(x) * sp.diff(x, t)
    assert verify_implicit_certificate(s, result.certificate).status.value == "verified"


def test_rate_cancellation_exposes_a_static_row_without_losing_its_domain():
    charge = sp.Mul(x, sp.Pow(x, -1, evaluate=False), evaluate=False)
    source = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(
            sp.diff(x, t) + y,
            sp.Derivative(charge, t, evaluate=False)
            + sp.Derivative(x**2, t, evaluate=False)
            - 2 * x * sp.diff(x, t)
            + y
            - x,
        ),
        interval=(-1, 1),
    )
    result = reduce_implicit_dae(source)
    assert result.reconstruction[y] == x
    assert sp.Ne(x, 0) in result.conditions


@pytest.mark.lean
def test_shifted_exponential_reconstruction_has_a_real_formal_proof():
    source = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, z, y),
        differential=(x, z),
        algebraic=(y,),
        residuals=(
            sp.diff(x, t) + sp.diff(y, t) + y,
            sp.diff(z, t) - x,
            y - sp.exp(x - z),
        ),
        interval=(-1, 1),
    )
    result = reduce_implicit_dae(source, proof="require", lean=LeanConfig(str(PROJECT)))
    assert result.formal_check.status.value == "verified"


@pytest.mark.parametrize("index", [0, 1])
def test_explicit_smooth_branch_retains_raw_charge_and_interval_guard(index):
    pw = sp.Piecewise((x**2, x < 0), (sp.exp(x), True))
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(sp.Derivative(pw, t, evaluate=False) + y, y - x),
        interval=(-1, 1),
        branch_choices=((pw, index),),
    )
    result = reduce_implicit_dae(s)
    assert s.residuals[0].has(pw)
    assert (sp.Lt(x, 0) if index == 0 else sp.Gt(x, 0)) in result.conditions
    expected = (2 * x if index == 0 else sp.exp(x)) * sp.diff(x, t) + x
    assert sp.expand(result.reduced_system.residuals[0] - expected) == 0
    assert result.coverage == "complete"


@pytest.mark.lean
@pytest.mark.parametrize("kind", ["structural", "exp", "low", "high"])
def test_kernel_checks_charge_normalization_and_reconstruction(kind):
    if kind == "structural":
        s, _ = structural()
    else:
        pw = sp.Piecewise((x**2, x < 0), (sp.exp(x), True))
        charge = sp.exp(x) if kind == "exp" else pw
        s = ImplicitDAESystem.create(
            time=t,
            unknowns=(x, y),
            differential=(x,),
            algebraic=(y,),
            residuals=(
                sp.Derivative(charge, t, evaluate=False) + y,
                y - charge if kind == "exp" else y - x,
            ),
            interval=(-1, 1),
            branch_choices=() if kind == "exp" else ((pw, 0 if kind == "low" else 1),),
        )
    result = reduce_implicit_dae(
        s, proof="require", lean=LeanConfig(str(PROJECT), timeout_seconds=180)
    )
    assert result.formal_check.status.value == "verified"
    if kind == "structural":
        assert "HasFDerivAt" in result.formal_check.source


@pytest.mark.lean
def test_kernel_rejects_losing_a_charge_partial():
    s, q = structural()
    result = reduce_implicit_dae(s)
    prefix, theorem = generate_lean(s, result.certificate).split(
        "theorem reduction_equivalence ", 1
    )
    statement, body = theorem.split(" := by", 1)
    left, right = statement.split(" ↔", 1)
    assert "uf_Qbe__d1" in right
    broken = (
        prefix
        + "theorem reduction_equivalence "
        + left
        + " ↔"
        + right.replace("uf_Qbe__d1", "uf_Qbe__d0")
        + " := by"
        + body
    )
    assert (
        compile_source(broken, config=LeanConfig(str(PROJECT))).status.value == "failed"
    )


@pytest.mark.lean
def test_terminal_charge_and_rate_balance_are_kernel_checked():
    be, bc = SmoothFunction("Qbe", 2), SmoothFunction("Qbc", 2)
    qbe, qbc = be.function(x, z), bc.function(x, z)
    charges = (-qbc, qbe + qbc, -qbe)
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, z),
        differential=(x, z),
        algebraic=(),
        residuals=(sum(sp.Derivative(v, t, evaluate=False) for v in charges),),
        interval=(-1, 1),
        smooth_functions=(be, bc),
    )
    assert sp.expand(sum(charges)) == 0
    result = reduce_implicit_dae(s, proof="require", lean=LeanConfig(str(PROJECT)))
    assert result.reduced_system.residuals == ()
    assert result.formal_check.status.value == "verified"


@pytest.mark.lean
def test_unary_smooth_law_composes_with_a_time_coordinate_chart(tmp_path):
    from equireduce import (
        TimeAffineTransform,
        export_artifact,
        load_artifact,
        reduce_implicit_in_coordinates,
    )

    law = SmoothFunction("Q", 1)
    q, r = (sp.Function(n, real=True)(t) for n in ("q", "r"))
    source = ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=(
            sp.Derivative(law.function(x), t, evaluate=False) + y,
            y - law.function(x),
        ),
        interval=(-1, 1),
        smooth_functions=(law,),
    )
    chart = TimeAffineTransform.create(
        source, variables=(q, r), matrix=((1, t), (0, 1)), offset=(t**2, 0)
    )
    result = reduce_implicit_in_coordinates(
        source,
        chart,
        differential=(q, r),
        algebraic=(),
        proof="require",
        lean=LeanConfig(str(PROJECT), timeout_seconds=180),
    )
    assert result.formal_check.status.value == "verified"
    path = export_artifact(result, tmp_path / "chart.json")
    assert load_artifact(path).certificate == result.certificate
