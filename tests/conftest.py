import os
import shutil
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def require_prepared_lean_for_marked_tests(request):
    if request.node.get_closest_marker("lean") is None:
        return
    project = Path(__file__).resolve().parents[1] / "lean"
    prepared = (
        project
        / ".lake/packages/mathlib/.lake/build/lib/lean/Mathlib/Tactic/Linarith.olean"
    )
    if shutil.which("lake") is None or not prepared.is_file():
        if os.environ.get("EQUIREDUCE_REQUIRE_LEAN") == "1":
            pytest.fail(
                "Lean tests are required but the pinned environment is not ready"
            )
        pytest.skip("prepare the pinned Lean environment to run formal tests")
