from pathlib import Path

import pytest
import sympy as sp

from equireduce import LeanConfig, reduce_in_coordinates, verify_certificate


def check_reduction(source, transform, candidates):
    result = reduce_in_coordinates(source, transform, candidates=candidates)
    assert len(result.remaining_unknowns) == 3
    assert verify_certificate(source, result.certificate).status.value == "verified"
    assert len(result.reconstruction) == len(source.unknowns)
    # All reconstruction expressions use only final coordinates and parameters.
    allowed = set(result.remaining_unknowns + source.parameters)
    assert all(
        value.free_symbols <= allowed for value in result.reconstruction.values()
    )
    return result


def test_bjt_voltage_difference_chart_reduces_four_equations_to_three():
    from examples.bjt43 import make_system

    source, transform, candidates = make_system()
    result = check_reduction(source, transform, candidates)
    ube, ubci, ubcx = result.remaining_unknowns
    re = next(item for item in source.parameters if str(item) == "rE")
    emitter = -re * sp.Function("Ie")(ube, ubci)
    assert result.reconstruction == dict(
        zip(
            source.unknowns,
            (ube + emitter, ube - ubci + emitter, emitter, ube - ubcx + emitter),
            strict=True,
        )
    )


def test_full_fourteen_equation_source_reduces_directly_to_three():
    from examples.bjt43 import make_full_system

    source, transform, candidates = make_full_system()
    assert len(source.unknowns) == 14
    result = check_reduction(source, transform, candidates)
    assert result.coverage == "complete"
    assert len(result.reduced_system.residuals) == 3


@pytest.mark.lean
@pytest.mark.parametrize("full", [False, True])
def test_kernel_checks_the_complete_bjt_coordinate_composition(full):
    from examples.bjt43 import make_full_system, make_system

    source, transform, candidates = (make_full_system if full else make_system)()
    result = reduce_in_coordinates(
        source,
        transform,
        candidates=candidates,
        proof="require",
        lean=LeanConfig(
            str(Path(__file__).resolve().parents[1] / "lean"), timeout_seconds=180
        ),
    )
    assert len(result.remaining_unknowns) == 3
    assert result.formal_check.status.value == "verified"
