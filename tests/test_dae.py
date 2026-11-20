from dataclasses import replace
from pathlib import Path

import pytest
import sympy as sp

from equireduce import (
    ArtifactError,
    DAESystem,
    InvalidSystemError,
    LeanConfig,
    UnsupportedDomainError,
    export_artifact,
    load_artifact,
    reduce_dae,
    verify_dae_certificate,
)

t = sp.Symbol("t", real=True)
x, y = (sp.Function(name, real=True)(t) for name in ("x", "y"))
a = sp.Symbol("a", real=True)


def example(*, constraints=None, conditions=()):
    return DAESystem.semi_explicit(
        time=t,
        differential=(x,),
        algebraic=(y,),
        rhs=(-y,),
        constraints=(y - x**2,) if constraints is None else constraints,
        interval=(0, 1),
        conditions=conditions,
    )


def test_dae_reduction_retains_actual_time_functions_and_derivatives():
    source = example()
    result = reduce_dae(source)
    assert result.reconstruction == {y: x**2}
    assert result.reduced_rhs == (-(x**2),)
    assert result.reduced_residuals == (sp.diff(x, t) + x**2,)
    assert result.reconstruction_derivatives == {sp.diff(y, t): 2 * x * sp.diff(x, t)}
    assert result.initial_check.status == "not_provided"
    assert result.domain_scope == "throughout_open_interval"
    assert verify_dae_certificate(source, result.certificate).status.value == "verified"
    assert result.formal_check.status.value == "not_requested"


def test_parameter_and_time_dependent_block_has_interval_wide_guards():
    source = DAESystem.semi_explicit(
        time=t,
        differential=(x,),
        algebraic=(y,),
        rhs=(-y,),
        constraints=(t * y - x,),
        interval=(0, 1),
    )
    result = reduce_dae(source)
    assert result.reconstruction[y] == x / t
    assert sp.Ne(t, 0) in result.conditions
    assert result.coverage == "conditional"
    assert (
        sp.simplify(
            result.reconstruction_derivatives[sp.diff(y, t)]
            - (sp.diff(x, t) / t - x / t**2)
        )
        == 0
    )


def test_dae_initial_data_is_checked_without_silent_correction():
    source = example()
    good = reduce_dae(
        source, initial_time=sp.Rational(1, 2), initial_values={x: 2, y: 4}
    )
    assert good.initial_check.status == "verified"
    with pytest.raises(InvalidSystemError, match="initial"):
        reduce_dae(source, initial_time=sp.Rational(1, 2), initial_values={x: 2, y: 3})
    symbolic = reduce_dae(
        source, initial_time=sp.Rational(1, 2), initial_values={x: a, y: 4}
    )
    assert symbolic.initial_check.status == "conditional"
    assert symbolic.initial_check.obligations
    with pytest.raises(InvalidSystemError, match="interval"):
        reduce_dae(source, initial_time=2, initial_values={x: 2, y: 4})


@pytest.mark.parametrize("constraints", [(y**2 - x,), (x,)])
def test_nonlinear_or_singular_algebraic_blocks_are_rejected(constraints):
    with pytest.raises(UnsupportedDomainError):
        reduce_dae(example(constraints=constraints))


@pytest.mark.parametrize(
    "rhs", [(sp.diff(y, t),), (sp.diff(x, t),), (sp.diff(x, t, 2),)]
)
def test_first_dae_contract_rejects_rates_on_the_rhs(rhs):
    with pytest.raises(UnsupportedDomainError):
        DAESystem.semi_explicit(
            time=t,
            differential=(x,),
            algebraic=(y,),
            rhs=rhs,
            constraints=(y - x**2,),
            interval=(0, 1),
        )


def test_nonsmooth_reconstruction_does_not_claim_classical_equivalence():
    with pytest.raises(UnsupportedDomainError):
        reduce_dae(example(constraints=(y - sp.Abs(x),)))


def test_dae_tampering_is_detected_independently():
    source = example()
    result = reduce_dae(source)
    bad = replace(result.certificate, reduced_rhs=(sp.S.One,))
    assert verify_dae_certificate(source, bad).status.value == "failed"


@pytest.mark.parametrize(
    "field,value", [("rhs", ("1",)), ("interval", ("0", 1)), ("conditions", (sp.true,))]
)
def test_dae_input_is_exact_and_never_parses_expression_strings(field, value):
    arguments = dict(
        time=t,
        differential=(x,),
        algebraic=(y,),
        rhs=(-y,),
        constraints=(y - x**2,),
        interval=(0, 1),
    )
    arguments[field] = value
    if field == "conditions":
        assert DAESystem.semi_explicit(**arguments).conditions == ()
    else:
        with pytest.raises(InvalidSystemError):
            DAESystem.semi_explicit(**arguments)


def test_reconstructed_rates_can_be_substituted_without_creating_higher_derivatives():
    result = reduce_dae(example())
    assert result.substitute_reconstructed_rates((sp.diff(y, t) + y,)).residuals == (
        2 * x * sp.diff(x, t) + x**2,
    )
    with pytest.raises(UnsupportedDomainError):
        result.substitute_reconstructed_rates((sp.diff(y, t, 2),))


def test_rate_substitution_preserves_a_pole_erased_by_cancellation():
    result = reduce_dae(example())
    original = sp.Mul(y, sp.Pow(y, -1, evaluate=False), evaluate=False)
    substituted = result.substitute_reconstructed_rates((original,))
    assert substituted.residuals == (sp.S.One,)
    assert sp.Ne(x, 0) in substituted.conditions
    from equireduce import verify_rate_substitution

    assert verify_rate_substitution(substituted).status.value == "verified"
    assert (
        verify_rate_substitution(replace(substituted, conditions=())).status.value
        == "failed"
    )


def test_dae_domains_are_read_before_replacing_states_by_slots():
    quotient = sp.Mul(y, sp.Pow(y, -1, evaluate=False), evaluate=False)
    source = DAESystem.semi_explicit(
        time=t,
        differential=(x,),
        algebraic=(y,),
        rhs=(quotient,),
        constraints=(y - x**2,),
        interval=(0, 1),
    )
    assert sp.Ne(y, 0) in source.conditions
    assert sp.Ne(x, 0) in reduce_dae(source).conditions


def test_dae_artifact_roundtrip_preserves_rates_and_checks_initial_metadata(tmp_path):
    import hashlib
    import json
    from importlib.resources import files

    from jsonschema import Draft202012Validator

    from equireduce.artifacts import _canonical

    result = reduce_dae(
        example(),
        initial_time=sp.Rational(1, 2),
        initial_values={x: 2, y: 4},
        proof="generate",
    )
    path = tmp_path / "dae.json"
    export_artifact(result, path)
    document = json.loads(path.read_text())
    Draft202012Validator(
        json.loads(
            files("equireduce")
            .joinpath("resources/artifact-v1.schema.json")
            .read_text()
        )
    ).validate(document)
    restored = load_artifact(path)
    assert restored.source == result.source
    assert restored.reconstruction_derivatives == result.reconstruction_derivatives
    assert restored.initial_check == result.initial_check
    assert restored.formal_check.origin == "recorded"
    # Recomputing a transport hash must not let forged mathematical metadata pass.
    document["payload"]["fields"]["initial_check"]["fields"]["status"] = "conditional"
    document["sha256"] = hashlib.sha256(_canonical(document["payload"])).hexdigest()
    path.write_text(json.dumps(document))
    with pytest.raises(ArtifactError):
        load_artifact(path)


@pytest.mark.lean
def test_lean_rejects_a_wrong_reconstruction_derivative():
    from equireduce import generate_lean
    from equireduce.lean import compile_source

    result = reduce_dae(example())
    proof = generate_lean(result.source, result.certificate)
    before, chain = proof.split("theorem reconstruction_chain_rule ", 1)
    statement, after = chain.split(" := by", 1)
    assert "(2 : ℝ)" in statement
    broken = (
        before
        + "theorem reconstruction_chain_rule "
        + statement.replace("(2 : ℝ)", "(3 : ℝ)")
        + " := by"
        + after
    )
    check = compile_source(
        broken, config=LeanConfig(str(Path(__file__).resolve().parents[1] / "lean"))
    )
    assert check.status.value == "failed"


@pytest.mark.lean
def test_two_state_time_dependent_rational_reconstruction_is_formally_checked():
    z, w = (sp.Function(name, real=True)(t) for name in ("z", "w"))
    source = DAESystem.semi_explicit(
        time=t,
        differential=(x, z),
        algebraic=(y, w),
        rhs=(-y + w, x - y),
        constraints=(2 * y + w - x**2, y - w - t * z),
        interval=(0, 1),
    )
    result = reduce_dae(
        source,
        proof="require",
        lean=LeanConfig(str(Path(__file__).resolve().parents[1] / "lean")),
    )
    assert result.formal_check.status.value == "verified"
    bad = replace(
        result.certificate, reconstruction_derivatives=((sp.diff(y, t), sp.S.Zero),)
    )
    assert verify_dae_certificate(source, bad).status.value == "failed"


@pytest.mark.lean
@pytest.mark.parametrize("case", ["polynomial", "rational", "parameter", "opaque_rhs"])
def test_real_lean_proves_trajectory_equivalence_and_reconstruction_chain_rule(
    case,
):
    source = example()
    if case == "rational":
        source = DAESystem.semi_explicit(
            time=t,
            differential=(x,),
            algebraic=(y,),
            rhs=(-y,),
            constraints=(t * y - x,),
            interval=(0, 1),
        )
    elif case == "parameter":
        source = DAESystem.semi_explicit(
            time=t,
            differential=(x,),
            algebraic=(y,),
            rhs=(-y,),
            constraints=(a * y - x,),
            interval=(0, 1),
            parameters=(a,),
        )
    elif case == "opaque_rhs":
        source = DAESystem.semi_explicit(
            time=t,
            differential=(x,),
            algebraic=(y,),
            rhs=(sp.Function("F")(t, x, y),),
            constraints=(y - x**2,),
            interval=(0, 1),
        )
    result = reduce_dae(
        source,
        proof="require",
        lean=LeanConfig(str(Path(__file__).resolve().parents[1] / "lean")),
    )
    assert result.formal_check.status.value == "verified"
    assert "HasDerivAt" in result.formal_check.source
    assert "Set.Ioo" in result.formal_check.source
    assert "reconstruction_chain_rule" in result.formal_check.source
