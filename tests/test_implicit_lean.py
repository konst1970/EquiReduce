from pathlib import Path

import pytest
import sympy as sp

from equireduce import ImplicitDAESystem, LeanConfig, reduce_implicit_dae
from equireduce.lean import compile_source, generate_lean

t, C, R, L, U0, a = sp.symbols("t C R L U0 a", real=True)
x, y, z = (sp.Function(n, real=True)(t) for n in ("x", "y", "z"))
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def source(case):
    if case == "rc":
        rows = ((y - x) / R + z, (x - y) / R + C * sp.diff(x, t), y - U0)
        variables = (y, x, z)
        algebraic = (y, z)
    elif case == "rl":
        rows = (y - U0, (z - y) / R + x, z - L * sp.diff(x, t))
        variables = (x, y, z)
        algebraic = (y, z)
    elif case == "chain":
        rows = (sp.diff(x, t) + sp.diff(y, t) + y, y - x**2)
        variables = (x, y)
        algebraic = (y,)
    elif case == "normalized":
        rows = (sp.Derivative(x**2, t, evaluate=False) + y, y - x)
        variables = (x, y)
        algebraic = (y,)
    elif case == "pole":
        quotient = sp.Mul(y, sp.Pow(y, -1, evaluate=False), evaluate=False)
        constraint = sp.Mul(quotient, y - 1, evaluate=False)
        rows = (sp.diff(x, t) + y, constraint)
        variables = (x, y)
        algebraic = (y,)
    elif case == "eliminated_charge":
        rows = (sp.diff(x, t) + sp.Derivative(y**2, t, evaluate=False), y - x**2)
        variables = (x, y)
        algebraic = (y,)
    else:
        rows = (sp.diff(x, t) + sp.diff(y, t) + y, a * y - x)
        variables = (x, y)
        algebraic = (y,)
    return ImplicitDAESystem.create(
        time=t,
        unknowns=variables,
        differential=(x,),
        algebraic=algebraic,
        residuals=rows,
        interval=(-1, 1),
        parameters=(C, R, L, U0, a),
    )


@pytest.mark.lean
@pytest.mark.parametrize(
    "case",
    ["rc", "rl", "chain", "normalized", "parameter", "pole", "eliminated_charge"],
)
def test_kernel_checks_the_full_original_implicit_trajectory_equivalence(case):
    s = source(case)
    result = reduce_implicit_dae(s, proof="require", lean=LeanConfig(str(PROJECT)))
    assert result.formal_check.status.value == "verified"
    assert "DifferentiableAt" in result.formal_check.source
    assert "deriv" in result.formal_check.source
    assert "Set.Ioo" in result.formal_check.source
    assert sp.Ne(C, 0) not in result.conditions


@pytest.mark.lean
def test_kernel_rejects_a_changed_implicit_target_equation():
    result = reduce_implicit_dae(source("chain"))
    text = generate_lean(result.source, result.certificate)
    prefix, theorem = text.split("theorem reduction_equivalence ", 1)
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
