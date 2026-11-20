from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    AffineTransform,
    InvalidSystemError,
    LeanConfig,
    System,
    export_artifact,
    load_artifact,
    reduce_in_coordinates,
    verify_certificate,
)

x, y, z, u, v, w, a = sp.symbols("x y z u v w a", real=True)
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def make_example():
    source = System.algebraic((x + y - 2, (x - y) ** 2 - 1), (x, y))
    transform = AffineTransform.create(
        source,
        variables=(u, v),
        matrix=((1, 1), (1, -1)),
    )
    return source, transform


def test_coordinates_expose_an_affine_variable_without_solving_the_nonlinearity():
    source, transform = make_example()
    result = reduce_in_coordinates(source, transform, candidates=(u,))
    assert result.source == source
    assert result.remaining_unknowns == (v,)
    assert sp.expand(result.reduced_system.residuals[0] - (4 * v**2 - 1)) == 0
    assert result.reconstruction == {x: 1 + v, y: 1 - v}
    assert result.coverage == "complete"
    assert result.coordinate_map == transform
    assert verify_certificate(source, result.certificate).status.value == "verified"


def test_coordinates_reject_unknown_proof_modes():
    source, transform = make_example()
    with pytest.raises(ValueError, match="proof"):
        reduce_in_coordinates(source, transform, proof="typo")


def test_parameter_dependent_inverse_adds_an_explicit_guard():
    source = System.algebraic((x + y - 1,), (x, y), parameters=(a,))
    transform = AffineTransform.create(
        source, variables=(u, v), matrix=((a, 0), (0, 1))
    )
    result = reduce_in_coordinates(source, transform, candidates=())
    assert result.coverage == "conditional"
    assert sp.Ne(a, 0) in result.additional_conditions
    assert dict(transform.inverse_map) == {u: x / a, v: y}


def test_original_domain_is_transported_before_rational_cancellation():
    source = System.algebraic((1 / x + y,), (x, y))
    transform = AffineTransform.create(
        source, variables=(u, v), matrix=((1, 1), (0, 1))
    )
    result = reduce_in_coordinates(source, transform, candidates=())
    assert sp.Ne(u + v, 0) in result.conditions
    assert result.coverage == "complete"


@pytest.mark.parametrize(
    "matrix", [((1, 1), (1, 1)), ((x, 0), (0, 1)), ((sp.Float("1.1"), 0), (0, 1))]
)
def test_invalid_or_singular_maps_are_rejected(matrix):
    source = System.algebraic((x + y,), (x, y))
    with pytest.raises(InvalidSystemError):
        AffineTransform.create(source, variables=(u, v), matrix=matrix)


def test_tampered_inverse_and_trace_cannot_pass_verification():
    source, transform = make_example()
    result = reduce_in_coordinates(source, transform, candidates=(u,))
    corrupted = replace(transform, inverse_matrix=sp.ImmutableMatrix.eye(2))
    forged = replace(result.certificate, transform=corrupted)
    assert verify_certificate(source, forged).status.value == "failed"
    inner = result.certificate.inner
    bad_core = replace(inner.reduction, reconstruction=((u, sp.S(9)),))
    forged = replace(result.certificate, inner=replace(inner, reduction=bad_core))
    assert verify_certificate(source, forged).status.value == "failed"


def test_composite_artifact_roundtrip_replays_both_certificates(tmp_path):
    source, transform = make_example()
    result = reduce_in_coordinates(source, transform, candidates=(u,))
    path = tmp_path / "coordinate.json"
    export_artifact(result, path)
    restored = load_artifact(path)
    assert restored.reconstruction == result.reconstruction
    assert restored.coordinate_map == transform
    assert verify_certificate(source, restored.certificate).status.value == "verified"


@pytest.mark.lean
@pytest.mark.parametrize("dimension", [2, 3])
def test_real_lean_checks_composition_from_original_to_final_coordinates(dimension):
    if dimension == 2:
        source, transform = make_example()
    else:
        source = System.algebraic((x + y - 2, (x - y) ** 2 - 1, z - y), (x, y, z))
        transform = AffineTransform.create(
            source, variables=(u, v, w), matrix=((1, 1, 0), (1, -1, 0), (0, 0, 1))
        )
    result = reduce_in_coordinates(
        source,
        transform,
        candidates=(u,),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified"
    assert "∃" in result.formal_check.source
    assert "augmented_equivalence" in result.formal_check.source


@pytest.mark.lean
def test_parameter_map_has_a_real_formal_inverse_proof():
    source = System.algebraic((x + y - 1,), (x, y), parameters=(a,))
    transform = AffineTransform.create(
        source, variables=(u, v), matrix=((a, 0), (0, 1))
    )
    result = reduce_in_coordinates(
        source, transform, candidates=(), proof="require", lean=LeanConfig(str(PROJECT))
    )
    assert result.formal_check.status.value == "verified"


@pytest.mark.lean
def test_polynomial_determinant_and_offset_are_formally_inverted():
    source = System.algebraic((x**2 + y - 1,), (x, y), parameters=(a,))
    transform = AffineTransform.create(
        source,
        variables=(u, v),
        matrix=((a, 1), (1, a)),
        offset=(1, -2),
    )
    result = reduce_in_coordinates(
        source, transform, candidates=(), proof="require", lean=LeanConfig(str(PROJECT))
    )
    assert result.formal_check.status.value == "verified"
    assert result.coverage == "conditional"


@pytest.mark.lean
def test_function_arguments_are_normalized_through_the_entire_chart():
    f = sp.Function("f")
    source = System.algebraic((x - y - a, f(x - y) + y), (x, y), parameters=(a,))
    transform = AffineTransform.create(
        source, variables=(u, v), matrix=((1, 1), (0, 1))
    )
    result = reduce_in_coordinates(
        source,
        transform,
        candidates=(u,),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.reconstruction == {x: a + v, y: v}
    assert result.formal_check.status.value == "verified"
