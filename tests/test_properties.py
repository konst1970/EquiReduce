from dataclasses import replace

import sympy as sp
from hypothesis import given, settings
from hypothesis import strategies as st

from equireduce import System, reduce_system, verify_certificate

x, y, z, a = sp.symbols("x y z a", real=True)


@given(st.integers(1, 9), st.integers(-9, 9), st.integers(-9, 9))
@settings(max_examples=25, deadline=None, derandomize=True)
def test_exact_rational_blocks_restore_every_original_row(scale, b, c):
    system = System.algebraic((scale * x + y - b, x - y - c), (x, y))
    result = reduce_system(system)
    assert result.remaining_unknowns == ()
    assert result.coverage == "complete"
    for row in system.residuals:
        assert sp.cancel(row.subs(result.reconstruction)) == 0
    assert verify_certificate(system, result.certificate).status.value == "verified"


def test_missing_original_domain_is_rejected_by_verifier():
    system = System.algebraic((y - 1 / x,), (x, y))
    result = reduce_system(system, candidates=(y,))
    forged = replace(
        result.certificate,
        reduction=replace(result.certificate.reduction, conditions=()),
    )
    assert verify_certificate(system, forged).status.value == "failed"


def test_nontrivial_inherited_condition_is_not_an_additional_guard():
    system = System.algebraic((y - 1 / (x - 1), x - a), (x, y), parameters=(a,))
    result = reduce_system(system)
    assert result.coverage == "complete"
    assert result.additional_conditions == ()


def test_zero_assumptions_do_not_make_a_fake_nonempty_verified_branch():
    system = System.algebraic(
        (a * y - 1,), (y,), parameters=(a,), conditions=(sp.Eq(a, 0),)
    )
    result = reduce_system(system)
    assert not result.reconstruction
    assert result.remaining_unknowns == (y,)


def test_affine_block_does_not_drop_a_nonlinear_constraint():
    system = System.algebraic((x + y - 2, x * y - 1), (x, y))
    result = reduce_system(system)
    assert len(result.reduced_system.residuals) == 1
    assert sp.cancel(result.reduced_system.residuals[0] + (y - 1) ** 2) == 0


def test_unsupported_formal_operation_stays_explicit():
    system = System.algebraic((y - x, sp.sin(y)), (x, y))
    result = reduce_system(system, candidates=(y,), proof="generate")
    assert result.formal_check.status.value == "unsupported"
