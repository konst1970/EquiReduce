import hashlib
import json
from importlib.resources import files

import pytest
import sympy as sp
from jsonschema import Draft202012Validator

from equireduce import (
    ArtifactError,
    ImplicitDAESystem,
    SmoothFunction,
    TimeAffineTransform,
    export_artifact,
    load_artifact,
    reduce_implicit_dae,
    reduce_implicit_in_coordinates,
    search_implicit_partitions,
)

t = sp.Symbol("t", real=True)
x, y, u, q, r = (sp.Function(n, real=True)(t) for n in ("x", "y", "u", "q", "r"))


def source():
    return ImplicitDAESystem.create(
        time=t,
        unknowns=(x, y),
        differential=(x,),
        algebraic=(y,),
        inputs=(u,),
        residuals=(sp.diff(x, t) + sp.diff(y, t) + y, y - x * u),
        interval=(-1, 1),
    )


@pytest.mark.parametrize("kind", ["manual", "search", "coordinate", "smooth", "branch"])
def test_implicit_roundtrip_replays_complete_math_and_initial_data(tmp_path, kind):
    s = source()
    initial = dict(
        initial_time=0,
        initial_values={x: 2},
        initial_input_values={u: 3},
        initial_input_rates={sp.diff(u, t): 5},
    )
    if kind == "search":
        result = search_implicit_partitions(s, preferred_differential=(x,), **initial)
    elif kind == "coordinate":
        chart = TimeAffineTransform.create(s, variables=(q, r), matrix=((1, 0), (t, 1)))
        initial["initial_values"] = {x: 2, y: 6}
        result = reduce_implicit_in_coordinates(
            s, chart, differential=(q,), algebraic=(r,), **initial
        )
    elif kind == "smooth":
        law = SmoothFunction("Q", 1)
        s = ImplicitDAESystem.create(
            time=t,
            unknowns=(x, y),
            differential=(x,),
            algebraic=(y,),
            residuals=(sp.diff(x, t) + sp.diff(y, t) + y, y - law.function(x)),
            interval=(-1, 1),
            smooth_functions=(law,),
        )
        result = reduce_implicit_dae(s, proof="generate")
    elif kind == "branch":
        pw = sp.Piecewise((x**2, x < 0), (sp.exp(x), True))
        s = ImplicitDAESystem.create(
            time=t,
            unknowns=(x, y),
            differential=(x,),
            algebraic=(y,),
            residuals=(sp.Derivative(pw, t, evaluate=False) + y, y - x),
            interval=(-1, 1),
            branch_choices=((pw, 1),),
        )
        result = reduce_implicit_dae(s, proof="generate")
    else:
        result = reduce_implicit_dae(s, **initial)
    path = export_artifact(result, tmp_path / kind)
    loaded = load_artifact(path)
    assert loaded.source == result.source
    assert loaded.certificate == result.certificate
    assert loaded.reconstruction_derivatives == result.reconstruction_derivatives
    assert loaded.initial_check == result.initial_check
    assert loaded.search == result.search
    assert loaded.formal_check.origin == "recorded"
    assert loaded.symbolic_check.status.value == "verified"
    schema = json.loads(
        files("equireduce")
        .joinpath("resources/artifact-implicit-v1.schema.json")
        .read_text()
    )
    Draft202012Validator(schema).validate(json.loads(path.read_text()))


@pytest.mark.parametrize(
    "field",
    ["coverage", "index_status", "reduced_system", "structure", "initial_check"],
)
def test_recomputed_checksum_cannot_hide_tampered_implicit_result(tmp_path, field):
    result = reduce_implicit_dae(
        source(), initial_time=0, initial_values={x: 2}, initial_input_values={u: 3}
    )
    path = export_artifact(result, tmp_path / "result.json")
    document = json.loads(path.read_text())
    data = document["payload"]["fields"]
    if field == "coverage":
        data[field] = "conditional"
    elif field == "index_status":
        data[field] = "index_one"
    elif field == "initial_check":
        data[field]["fields"]["status"] = "verified"
    elif field == "structure":
        data[field]["fields"]["reason"] = "invented"
    else:
        data[field]["fields"]["residuals"]["args"] = []
        data[field]["fields"]["residual_names"]["args"] = []
    document["sha256"] = hashlib.sha256(
        json.dumps(
            document["payload"],
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()
    path.write_text(json.dumps(document))
    with pytest.raises(ArtifactError):
        load_artifact(path)
