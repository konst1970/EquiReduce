from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    LeanConfig,
    ReductionOptions,
    System,
    benchmark_coordinates,
    export_artifact,
    load_artifact,
    reduce_system,
    search_coordinates,
)

x, y, a, b = sp.symbols("x y a b", real=True)
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def make_example():
    return System.algebraic((x + y - a, (x - y) ** 2 - b), (x, y), parameters=(a, b))


def test_budget_is_explicit_and_does_not_claim_complete_search():
    result = search_coordinates(
        make_example(), options=ReductionOptions(max_candidates=1)
    )
    assert result.search.candidates_evaluated == 1
    assert result.search.candidates_available > 1
    assert not result.search.complete
    assert len(result.search.evaluated) == 1


def test_full_finite_family_is_deterministic_and_simplifies_the_jacobian():
    options = ReductionOptions(max_candidates=100)
    first = search_coordinates(make_example(), options=options)
    second = search_coordinates(make_example(), options=options)
    assert first.search.complete
    assert first.search.candidates_evaluated == first.search.candidates_available
    assert first.coordinate_map == second.coordinate_map
    assert first.reduced_system == second.reduced_system
    assert first.metrics.reduced_jacobian_operations <= 1
    assert len(first.remaining_unknowns) == 1


def test_public_options_dispatch_to_search_and_preserve_the_source():
    source = make_example()
    result = reduce_system(
        source, options=ReductionOptions(coordinate_search=True, max_candidates=3)
    )
    assert result.source is source
    assert result.search.candidates_evaluated == 3
    assert source.unknowns == (x, y)


def test_search_metadata_and_matrix_roundtrip(tmp_path):
    result = search_coordinates(
        make_example(), options=ReductionOptions(max_candidates=4)
    )
    path = tmp_path / "search.json"
    export_artifact(result, path)
    restored = load_artifact(path)
    assert restored.search == result.search
    assert restored.metrics == result.metrics


def test_shared_reference_charts_are_included_early():
    z = sp.Symbol("z", real=True)
    f = sp.Function("f")
    source = System.algebraic((f(x - z, y - z), z - f(x - z, y - z)), (x, y, z))
    result = search_coordinates(source, options=ReductionOptions(max_candidates=4))
    assert len(result.remaining_unknowns) == 2
    assert result.search.candidates_evaluated == 4


def test_truncated_report_cannot_be_relabelled_as_complete():
    result = search_coordinates(
        make_example(), options=ReductionOptions(max_candidates=1)
    )
    with pytest.raises(ValueError, match="complete"):
        replace(result.search, complete=True)


def test_benchmark_rejects_a_report_from_another_source():
    result = search_coordinates(
        make_example(), options=ReductionOptions(max_candidates=1)
    )
    other = System.algebraic((x + y - 99, (x - y) ** 2 - b), (x, y), parameters=(b,))
    with pytest.raises(ValueError, match="source"):
        benchmark_coordinates(other, result.search, max_candidates=1)


@pytest.mark.lean
def test_selected_candidate_is_really_compiled():
    result = search_coordinates(
        make_example(),
        options=ReductionOptions(max_candidates=12),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified"
    assert result.search.best_index >= 0


@pytest.mark.lean
def test_benchmark_records_actual_time_and_does_not_invent_correlation():
    source = make_example()
    result = search_coordinates(source, options=ReductionOptions(max_candidates=4))
    benchmark = benchmark_coordinates(
        source, result.search, max_candidates=1, lean=LeanConfig(str(PROJECT))
    )
    assert benchmark.candidates_attempted == 1
    assert benchmark.entries[0].verification.status.value == "verified"
    assert benchmark.entries[0].seconds > 0
    assert benchmark.spearman_correlation is None
    record = benchmark.to_record()
    assert (
        record["entries"][0]["mathlib_revision"]
        == "fc4f59e577feb1a4956671bc04ac18aaaf8cd842"
    )
