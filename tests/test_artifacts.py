import hashlib
import json
from dataclasses import replace
from importlib.resources import files

import pytest
import sympy as sp
from jsonschema import Draft202012Validator, ValidationError

from equireduce import (
    ArtifactError,
    System,
    export_artifact,
    load_artifact,
    reduce_system,
)


def test_exact_roundtrip_and_symbol_assumptions(tmp_path):
    x, y, a = sp.symbols("x y a", real=True)
    source = System.algebraic(
        (a * y - x, y + x - sp.Rational(1, 3)), (x, y), parameters=(a,)
    )
    result = reduce_system(source, candidates=(y,), proof="generate")
    path = tmp_path / "artifact.json"
    export_artifact(result, path)
    assert json.loads(path.read_text())["versions"]["sympy"] == sp.__version__
    restored = load_artifact(path)
    assert restored.source == source
    assert restored.reduced_system == result.reduced_system
    assert restored.reconstruction == result.reconstruction
    assert restored.formal_check.source == result.formal_check.source
    assert restored.formal_check.origin == "recorded"


def test_mixed_same_named_symbols_keep_identity(tmp_path):
    positive = sp.Symbol("x", positive=True)
    real = sp.Symbol("x", real=True)
    system = System.algebraic((positive - real,), (positive, real))
    path = tmp_path / "artifact.json"
    export_artifact(reduce_system(system), path)
    restored = load_artifact(path)
    assert restored.source.unknowns == (positive, real)
    assert len(set(restored.source.unknowns)) == 2


def test_corrupted_hash_and_unknown_schema_are_rejected(tmp_path):
    x = sp.Symbol("x", real=True)
    path = tmp_path / "artifact.json"
    export_artifact(reduce_system(System.algebraic((x - 1,), (x,))), path)
    data = json.loads(path.read_text())
    data["sha256"] = "0" * 64
    path.write_text(json.dumps(data))
    with pytest.raises(ArtifactError, match="hash"):
        load_artifact(path)
    data["schema"] = "equireduce.reduction/v999"
    path.write_text(json.dumps(data))
    with pytest.raises(ArtifactError, match="schema"):
        load_artifact(path)


def test_no_executable_expression_parser(tmp_path):
    path = tmp_path / "artifact.json"
    path.write_text(
        json.dumps(
            {
                "schema": "equireduce.reduction/v1",
                "payload": "__import__('os').system('false')",
            }
        )
    )
    with pytest.raises(ArtifactError):
        load_artifact(path)


def test_directory_bundle_contains_proof_and_pinned_versions(tmp_path):
    x = sp.Symbol("x", real=True)
    result = reduce_system(System.algebraic((x - 1,), (x,)), proof="generate")
    export_artifact(result, tmp_path / "bundle")
    for name in (
        "artifact.json",
        "proof.lean",
        "lean-toolchain",
        "lakefile.toml",
        "lake-manifest.json",
        "verification.json",
        "README.md",
    ):
        assert (tmp_path / "bundle" / name).is_file()
    assert load_artifact(tmp_path / "bundle").reconstruction == {x: 1}


def test_mathematical_hash_is_independent_of_run_metadata(tmp_path):
    x = sp.Symbol("x", real=True)
    result = reduce_system(System.algebraic((x - 1,), (x,)))
    changed = replace(
        result, formal_check=replace(result.formal_check, output="another run")
    )
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    export_artifact(result, first)
    export_artifact(changed, second)
    one, two = json.loads(first.read_text()), json.loads(second.read_text())
    assert one["mathematical_sha256"] == two["mathematical_sha256"]
    assert one["sha256"] != two["sha256"]


def test_recomputed_checksum_cannot_hide_wrong_coverage(tmp_path):
    x, a = sp.symbols("x a", real=True)
    result = reduce_system(System.algebraic((a * x - 1,), (x,), parameters=(a,)))
    path = tmp_path / "artifact.json"
    export_artifact(result, path)
    document = json.loads(path.read_text())
    document["payload"]["fields"]["coverage"] = "complete"
    payload = json.dumps(
        document["payload"], sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    document["sha256"] = hashlib.sha256(payload).hexdigest()
    path.write_text(json.dumps(document))
    with pytest.raises(ArtifactError, match="coverage"):
        load_artifact(path)


def test_function_assumptions_survive_portable_roundtrip(tmp_path):
    x = sp.Symbol("x", real=True)
    f = sp.Function("f", real=True)
    source = System.algebraic((f(x),), (x,))
    path = tmp_path / "artifact.json"
    export_artifact(reduce_system(source), path)
    assert load_artifact(path).source == source


def test_machine_schema_accepts_real_artifact_and_rejects_unknown_ast(tmp_path):
    schema = json.loads(
        files("equireduce").joinpath("resources", "artifact-v1.schema.json").read_text()
    )
    Draft202012Validator.check_schema(schema)
    validator = Draft202012Validator(schema)
    x = sp.Symbol("x", real=True)
    path = tmp_path / "artifact.json"
    export_artifact(reduce_system(System.algebraic((x - 1,), (x,))), path)
    document = json.loads(path.read_text())
    validator.validate(document)
    document["payload"] = {"t": "execute_python", "code": "arbitrary"}
    with pytest.raises(ValidationError):
        validator.validate(document)


def test_unevaluated_source_keeps_structure_and_excluded_pole(tmp_path):
    x = sp.Symbol("x", real=True)
    expression = sp.Mul(x - 1, sp.Pow(x - 1, -1, evaluate=False), evaluate=False)
    system = System.algebraic((expression,), (x,))
    path = tmp_path / "artifact.json"
    export_artifact(reduce_system(system, candidates=()), path)
    restored = load_artifact(path)
    assert restored.source == system
    assert sp.Ne(x - 1, 0) in restored.source.conditions


def test_excessive_power_is_rejected_before_evaluation():
    from equireduce.artifacts import Codec

    node = {
        "t": "expr",
        "name": "Pow",
        "args": [{"t": "integer", "v": "2"}, {"t": "integer", "v": "10001"}],
    }
    with pytest.raises(ArtifactError, match="limit"):
        Codec().decode(node)
