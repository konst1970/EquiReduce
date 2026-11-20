from dataclasses import replace

import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    analyze_implicit_dae,
    analyze_symbolic_rank,
    verify_implicit_structure,
)
from equireduce.conditions import symbolic_zero_status

t, a = sp.symbols("t a", real=True)
x, y, u = (sp.Function(name, real=True)(t) for name in ("x", "y", "u"))


def source(rows, **kwargs):
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        residuals=rows,
        interval=(-1, 1),
        parameters=(a,),
        **kwargs,
    )


def test_normalization_uses_the_exact_chain_rule_and_retains_original_rows():
    row = sp.Derivative(x**2 + t * x, t, evaluate=False) + sp.diff(y, t) + a * y
    original = source((row, y - x))
    analysis = analyze_implicit_dae(original)
    assert analysis.status.value == "affine"
    assert analysis.mass_matrix == sp.ImmutableMatrix(((2 * x + t, 1), (0, 0)))
    assert analysis.offset == sp.ImmutableMatrix((x + a * y, y - x))
    assert original.residuals[0] == row
    assert analysis.derivatives == (sp.diff(x, t), sp.diff(y, t))
    assert analysis.normalization.rewrites
    assert verify_implicit_structure(analysis).status.value == "verified"


@pytest.mark.parametrize("row", [sp.diff(x, t) ** 2, sp.sin(sp.diff(x, t))])
def test_nonlinear_rate_terms_are_not_misclassified_by_their_jacobian(row):
    analysis = analyze_implicit_dae(source((row, y - x)))
    assert analysis.status.value == "non_affine"
    assert analysis.rank is None


def test_an_opaque_function_of_a_rate_has_unknown_affinity():
    f = sp.Function("f", real=True)
    analysis = analyze_implicit_dae(source((f(sp.diff(x, t)), y - x)))
    assert analysis.status.value == "unknown"
    assert analysis.rank is None


def test_external_input_rates_remain_exogenous_and_are_not_unknown_states():
    analysis = analyze_implicit_dae(
        source((sp.diff(x, t) + u * sp.diff(y, t) - sp.diff(u, t), y - x), inputs=(u,))
    )
    assert analysis.mass_matrix == sp.ImmutableMatrix(((1, u), (0, 0)))
    assert analysis.offset[0] == -sp.diff(u, t)
    assert analysis.input_derivatives == (sp.diff(u, t),)


def test_rank_guards_are_diagnostic_and_are_not_added_to_the_system_domain():
    analysis = analyze_implicit_dae(source((a * sp.diff(x, t) + y, y - x)))
    assert analysis.rank.status == "conditional"
    assert analysis.rank.rank == 1
    assert analysis.rank.conditions == (sp.Ne(a, 0),)
    assert sp.Ne(a, 0) not in analysis.normalization.conditions


def test_rank_distinguishes_exact_conditional_and_unknown():
    exact = analyze_symbolic_rank(((1, a), (0, 0)))
    assert (exact.status, exact.rank, exact.lower_bound, exact.upper_bound) == (
        "exact",
        1,
        1,
        1,
    )
    conditional = analyze_symbolic_rank(((1, 0), (0, a)))
    assert (
        conditional.status,
        conditional.rank,
        conditional.lower_bound,
        conditional.upper_bound,
    ) == ("conditional", 2, 1, 2)
    assert conditional.conditions == (sp.Ne(a, 0),)
    f = sp.Function("f")(a)
    unknown = analyze_symbolic_rank(((f,),))
    assert (unknown.status, unknown.rank, unknown.lower_bound, unknown.upper_bound) == (
        "unknown",
        None,
        0,
        1,
    )
    known = analyze_symbolic_rank(((f,),), conditions=(sp.Ne(f, 0),))
    assert (known.status, known.rank) == ("exact", 1)


def test_rank_budget_and_zero_dimensions_are_explicit():
    report = analyze_symbolic_rank(((a, 0), (0, 1)), max_minors=1)
    assert report.budget_exhausted
    assert report.minors_examined == 1
    assert report.upper_bound == 2
    zero = analyze_symbolic_rank(sp.ImmutableMatrix.zeros(0, 3))
    assert (zero.status, zero.rank) == ("exact", 0)
    for budget in (0, True, -1):
        with pytest.raises(ValueError):
            analyze_symbolic_rank(((1,),), max_minors=budget)


def test_corrupted_structure_or_normalization_cannot_verify():
    analysis = analyze_implicit_dae(source((sp.diff(x, t) + y, y - x)))
    bad = replace(analysis, mass_matrix=sp.ImmutableMatrix.zeros(2, 2))
    assert verify_implicit_structure(bad).status.value == "failed"
    malformed = replace(analysis, normalization=None)
    assert verify_implicit_structure(malformed).status.value == "failed"
    bad = replace(
        analysis,
        normalization=replace(analysis.normalization, residuals=(sp.S.Zero, sp.S.Zero)),
    )
    assert verify_implicit_structure(bad).status.value == "failed"


def test_identity_checks_do_not_use_equals_numeric_heuristics(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Expr.equals may use numerical probing")

    monkeypatch.setattr(sp.Expr, "equals", forbidden)
    assert symbolic_zero_status(a * (a + 1)).value == "not_identically_zero"
