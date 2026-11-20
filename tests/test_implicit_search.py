import pytest
import sympy as sp

from equireduce import (
    ImplicitDAESystem,
    search_implicit_partitions,
    verify_implicit_certificate,
)

t, R, C, U = sp.symbols("t R C U", real=True)
vin, v, i = (sp.Function(n, real=True)(t) for n in ("vin", "v", "i"))


def source():
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(vin, v, i),
        differential=(vin, v, i),
        algebraic=(),
        residuals=((vin - v) / R + i, (v - vin) / R + C * sp.diff(v, t), vin - U),
        parameters=(R, C, U),
        interval=(-1, 1),
    )


def test_automatic_partition_finds_a_checked_rc_reduction():
    s = source()
    result = search_implicit_partitions(
        s, max_candidates=16, preferred_differential=(v,)
    )
    assert result.remaining_unknowns == (v,)
    assert result.search.source == s
    assert result.search.complete
    assert result.search.candidates_evaluated <= 16
    assert (
        verify_implicit_certificate(result.source, result.certificate).status.value
        == "verified"
    )
    assert sp.Ne(C, 0) not in result.conditions


def test_budget_and_tie_breaking_are_deterministic():
    s = source()
    a = search_implicit_partitions(s, max_candidates=1)
    b = search_implicit_partitions(s, max_candidates=1)
    assert not a.search.complete
    assert a.search.candidates_evaluated == 1
    assert a.source == b.source
    assert a.certificate == b.certificate


def test_no_static_rows_does_not_invent_an_algebraic_block_or_index_claim():
    s = ImplicitDAESystem.create(
        time=t,
        unknowns=(v, i),
        differential=(v, i),
        algebraic=(),
        residuals=(sp.diff(v, t) + i, sp.diff(i, t) - v),
        interval=(-1, 1),
    )
    result = search_implicit_partitions(s, max_candidates=10)
    assert result.remaining_unknowns == (v, i)
    assert result.search.complete
    assert result.index_status == "not_classified"


@pytest.mark.parametrize("budget", [0, True, -1])
def test_invalid_search_budgets_are_rejected(budget):
    with pytest.raises(ValueError):
        search_implicit_partitions(source(), max_candidates=budget)
