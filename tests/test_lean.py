import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import LeanConfig, ProofVerificationError, System, reduce_system
from equireduce.lean import generate_lean, verify_with_lean

x, y, a, b = sp.symbols("x y a b", real=True)
PROJECT = Path(__file__).resolve().parents[1] / "lean"


def test_generate_is_not_a_claim_of_verification():
    system = System.algebraic((a * y - x,), (x, y), parameters=(a,))
    result = reduce_system(system, candidates=(y,), proof="generate")
    assert result.formal_check.status.value == "generated"
    assert "theorem reduction_equivalence" in result.formal_check.source
    assert "#print axioms reduction_equivalence" in result.formal_check.source


def test_required_proof_has_no_fallback_without_lean(tmp_path):
    system = System.algebraic((y - x,), (x, y))
    with pytest.raises(ProofVerificationError) as error:
        reduce_system(
            system,
            candidates=(y,),
            proof="require",
            lean=LeanConfig(str(tmp_path), command=("no-such-lean-executable",)),
        )
    assert error.value.verification.status.value == "unavailable"
    assert error.value.candidate.reconstruction[y] == x


def test_lean_names_are_deterministic_for_same_named_symbols(tmp_path):
    code = """
import sympy as s
from equireduce import System, reduce_system
x, y = s.Symbol('x', positive=True), s.Symbol('x', real=True)
system = System.algebraic((x-y,), (x,y))
print(reduce_system(system, candidates=(), proof='generate').formal_check.source)
"""
    outputs = []
    for seed in ("1", "2", "3"):
        environment = {
            **os.environ,
            "PYTHONHASHSEED": seed,
            "PYTHONPATH": str(PROJECT.parent / "src"),
        }
        outputs.append(
            subprocess.run(
                [sys.executable, "-c", code],
                cwd=tmp_path,
                env=environment,
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    assert len(set(outputs)) == 1


@pytest.mark.lean
@pytest.mark.parametrize(
    "kind", ["scalar", "block", "opaque", "parameter-block", "empty"]
)
def test_real_lean_equivalence(kind):
    f = sp.Function("f")
    systems = {
        "scalar": System.algebraic((a * y - x, y + x - 1), (x, y), parameters=(a,)),
        "block": System.algebraic((x + y - a, x - y - b), (x, y), parameters=(a, b)),
        "opaque": System.algebraic((y - x**2, f(y) + x - a), (x, y), parameters=(a,)),
        "parameter-block": System.algebraic(
            (a * x + y - b, x + a * y - 1), (x, y), parameters=(a, b)
        ),
        "empty": System.algebraic((), (x,)),
    }
    system = systems[kind]
    candidates = (y,) if kind in ("scalar", "opaque") else None
    result = reduce_system(
        system,
        candidates=candidates,
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified", result.formal_check.output
    assert result.formal_check.command
    assert result.formal_check.seconds > 0
    assert result.formal_check.checked_at_utc
    assert set(result.formal_check.axioms) <= {
        "propext",
        "Classical.choice",
        "Quot.sound",
    }
    assert (
        result.formal_check.mathlib_revision
        == "fc4f59e577feb1a4956671bc04ac18aaaf8cd842"
    )


@pytest.mark.lean
def test_actual_compiler_rejects_wrong_reduced_equation_and_missing_guard():
    system = System.algebraic((a * y - x, y + x - 1), (x, y), parameters=(a,))
    result = reduce_system(system, candidates=(y,))
    source = generate_lean(system, result.certificate)
    config = LeanConfig(str(PROJECT))
    assert (
        verify_with_lean(system, result.certificate, config=config).status.value
        == "verified"
    )
    from equireduce.lean import compile_source

    changed = source.replace(
        "theorem reduction_equivalence",
        "axiom injected : False\n\ntheorem reduction_equivalence",
    )
    assert compile_source(changed, config=config).status.value == "failed"
    malformed = replace(result.certificate.reduction, conditions=())
    forged = replace(result.certificate, reduction=malformed)
    assert verify_with_lean(system, forged, config=config).status.value == "failed"


@pytest.mark.lean
@pytest.mark.parametrize("functional", [False, True])
def test_implicit_sympy_sign_assumptions_are_explicit_in_lean(functional):
    positive = sp.Symbol("p", positive=True)
    coefficient = sp.Function("gain", positive=True)(x) if functional else positive
    system = System.algebraic(
        (coefficient * y - 1,),
        (x, y),
        parameters=() if functional else (positive,),
    )
    result = reduce_system(
        system,
        candidates=(y,),
        proof="require",
        lean=LeanConfig(str(PROJECT)),
    )
    assert result.formal_check.status.value == "verified"
    assert "hCond" in result.formal_check.source
