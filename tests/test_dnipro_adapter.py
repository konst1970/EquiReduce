import importlib
import sys
from pathlib import Path

import pytest
import sympy as sp

from equireduce import InvalidSystemError, UnsupportedDomainError


@pytest.fixture(scope="module")
def adapter_module():
    root = Path(__file__).resolve().parents[2]
    if not (root / "dnipro").is_dir():
        pytest.skip("Dnipro adapter integration requires the parent Dnipro checkout")
    sys.path.insert(0, str(root))
    return importlib.import_module("dnipro.analysis.equireduce_adapter")


def residual_system(unknowns, residuals, domain="dc"):
    cls = importlib.import_module("dnipro.mna.residual_system").ResidualSystem
    return cls(domain, list(unknowns), list(residuals), [], [], [], {})


def test_dc_realization_is_explicit_and_preserves_the_original_input(adapter_module):
    x, y, a = sp.symbols("x y a")
    source = residual_system((x, y), (a * y - x, y + x - 1))
    with pytest.raises(InvalidSystemError, match="real"):
        adapter_module.from_dc_system(source)
    adapter = adapter_module.from_dc_system(source, assume_real=True)
    assert adapter.real_domain_assumed
    assert adapter.symbol_map[x].is_real is True
    assert source.unknowns == [x, y]
    assert source.residuals[0] == a * y - x
    result = adapter.reduce(candidates=(y,))
    assert adapter.restore_reconstruction(result)[y] == x / a


def test_time_domain_is_not_just_renamed_dc(adapter_module):
    t = sp.Symbol("t", real=True)
    x = sp.Function("x")(t)
    source = residual_system((x,), (sp.diff(x, t) + x,), "time")
    with pytest.raises(UnsupportedDomainError):
        adapter_module.from_dc_system(source, assume_real=True)


def test_stationary_projection_sets_only_declared_state_rates_to_zero(adapter_module):
    t = sp.Symbol("t", real=True)
    x, y = sp.Function("x")(t), sp.Function("y")(t)
    source = residual_system((x, y), (sp.diff(x, t) / (x - 1) + y, x - y), "time")
    adapter = adapter_module.stationary_from_time(source, assume_real=True)
    xr, yr = adapter.symbol_map[x], adapter.symbol_map[y]
    assert adapter.origin == "stationary"
    assert adapter.system.residuals == (yr, xr - yr)
    assert sp.Ne(xr - 1, 0) in adapter.system.conditions
    assert not any(row.has(t, sp.Derivative) for row in adapter.system.residuals)
    assert source.residuals[0].has(sp.Derivative)


def test_stationary_projection_rejects_a_time_varying_input(adapter_module):
    t = sp.Symbol("t", real=True)
    x = sp.Function("x")(t)
    source = residual_system((x,), (sp.diff(x, t) + x - sp.sin(t),), "time")
    with pytest.raises(UnsupportedDomainError, match="time"):
        adapter_module.stationary_from_time(source, assume_real=True)


def test_stationary_projection_rejects_unknown_higher_order_rates(adapter_module):
    t = sp.Symbol("t", real=True)
    x = sp.Function("x")(t)
    source = residual_system((x,), (sp.diff(x, t, 2) + x,), "time")
    with pytest.raises(UnsupportedDomainError):
        adapter_module.stationary_from_time(source, assume_real=True)


def test_stationary_projection_preserves_declared_signs(adapter_module):
    t = sp.Symbol("t", real=True)
    x = sp.Function("x", positive=True)(t)
    source = residual_system((x,), (sp.diff(x, t) + x - 1,), "time")
    adapter = adapter_module.stationary_from_time(source)
    xr = adapter.symbol_map[x]
    assert xr.is_positive is True
    assert sp.Gt(xr, 0, evaluate=False) in adapter.system.conditions


def test_stationary_projection_cannot_reinterpret_an_imaginary_state_as_real(
    adapter_module,
):
    t = sp.Symbol("t", real=True)
    x = sp.Function("x", imaginary=True)(t)
    source = residual_system((x,), (x,), "time")
    with pytest.raises(InvalidSystemError, match="real"):
        adapter_module.stationary_from_time(source, assume_real=True)


def test_dc_adapter_matches_legacy_reduction_without_changing_the_model(adapter_module):
    legacy = importlib.import_module("dnipro.analysis.reduction")
    x, y, a = sp.symbols("x y a", real=True)
    source = residual_system((x, y), (a * y - x, y + x - 1))
    old = legacy.reduce_affine_system(source, candidates=(y,))
    result = adapter_module.from_dc_system(source).reduce(candidates=(y,))
    assert result.remaining_unknowns == old.reduced_unknowns
    assert result.reconstruction == dict(old.reconstruction)
    assert result.reduced_system.residuals == old.reduced_residuals
