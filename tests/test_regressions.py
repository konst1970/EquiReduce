import importlib.util
from pathlib import Path

import pytest
import sympy as sp

from equireduce import LeanConfig, System, export_artifact, reduce_system
from equireduce.lean import compile_source, generate_lean

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.lean
@pytest.mark.parametrize("name", ["flow_balance", "kinematic"])
def test_nonelectrical_examples_have_real_formal_proofs(name):
    spec = importlib.util.spec_from_file_location(
        name, ROOT / "examples" / f"{name}.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    system, candidates = module.make_system()
    result = reduce_system(
        system,
        candidates=candidates,
        proof="require",
        lean=LeanConfig(str(ROOT / "lean")),
    )
    assert result.formal_check.status.value == "verified"
    assert len(result.remaining_unknowns) < len(system.unknowns)


@pytest.mark.lean
def test_new_pipeline_verifies_all_fourteen_original_equations(tmp_path):
    spec = importlib.util.spec_from_file_location("bjt14", ROOT / "examples/bjt14.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    system, candidates = module.make_system()
    result = reduce_system(
        system,
        candidates=candidates,
        proof="require",
        lean=LeanConfig(str(ROOT / "lean")),
    )
    assert len(result.source.residuals) == 14
    assert len(result.reduced_system.residuals) == 4
    assert len(result.remaining_unknowns) == 4
    assert len(result.reconstruction) == 10
    assert result.coverage == "complete"
    export_artifact(result, tmp_path / "bjt14")


@pytest.mark.lean
def test_lean_rejects_mathematically_wrong_target_not_just_missing_import():
    x, y = sp.symbols("x y", real=True)
    system = System.algebraic((y - x, x + y - 2), (x, y))
    result = reduce_system(system, candidates=(y,))
    source = generate_lean(system, result.certificate)
    # Alter only the target proposition; keep all hypotheses and the proof body.
    start = source.index("    (")
    end = source.index(" := by", start)
    statement = source[start:end]
    assert "(-2 : ℝ)" in statement
    premise, target = statement.split("↔", 1)
    changed = (
        source[:start]
        + premise
        + "↔"
        + target.replace("(-2 : ℝ)", "(-3 : ℝ)")
        + source[end:]
    )
    config = LeanConfig(str(ROOT / "lean"))
    assert compile_source(source, config=config).status.value == "verified"
    failed = compile_source(changed, config=config)
    assert failed.status.value == "failed"
    assert failed.returncode != 0
    assert "error:" in failed.output
