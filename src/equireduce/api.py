"""Public reduction operations independent of any application model."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import replace
from typing import Literal

import sympy as sp

from equireduce import _core
from equireduce.conditions import (
    assumption_consistency,
    normalize_conditions,
    simplify_condition,
)
from equireduce.errors import CertificateError, InvalidSystemError
from equireduce.metrics import measure
from equireduce.result import (
    Certificate,
    CoordinateCertificate,
    LeanConfig,
    ReductionOptions,
    ReductionResult,
)
from equireduce.system import System


def _canonical(conditions):
    values = []
    for value in conditions:
        simplified = simplify_condition(value)
        if (
            simplified is sp.true
            and value is not sp.true
            and (value.free_symbols or value.has(sp.core.function.AppliedUndef))
        ):
            simplified = value
        values.append(simplified)
    return normalize_conditions(values)


def verify_certificate(
    system: System, certificate: Certificate | CoordinateCertificate
) -> _core.CertificateVerification:
    """Replay a certificate against the caller's original system."""
    if isinstance(certificate, CoordinateCertificate):
        from equireduce.coordinates import verify_coordinate_certificate

        return verify_coordinate_certificate(system, certificate)
    fail = _core.CertificateVerification
    failed = _core.CertificateStatus.FAILED
    if not isinstance(certificate, Certificate) or certificate.source != system:
        return fail(failed, ("certificate belongs to a different source system",))
    core = certificate.reduction
    if (
        core.source_unknowns != system.unknowns
        or core.source_residuals != system.residuals
        or core.source_residual_names != system.residual_names
    ):
        return fail(failed, ("source snapshot does not match input",))
    reconstruction = dict(core.reconstruction)
    images = _canonical(
        value.subs(reconstruction, simultaneous=True) for value in system.conditions
    )
    if any(value not in _canonical(core.conditions) for value in images):
        return fail(failed, ("source domain condition was dropped",))
    final_variables = set(core.reduced_unknowns) | set(system.parameters)
    if any(
        not value.free_symbols <= final_variables for value in reconstruction.values()
    ):
        return fail(
            failed, ("reconstruction contains eliminated or undeclared symbols",)
        )
    return _core.verify_reduction_certificate(core)


def reduce_system(
    system: System,
    *,
    candidates: Sequence[sp.Symbol] | None = None,
    options: ReductionOptions | None = None,
    proof: Literal["none", "generate", "require"] = "none",
    lean: LeanConfig | None = None,
) -> ReductionResult:
    """Reduce an exact real algebraic system and independently check the trace."""
    if not isinstance(system, System):
        raise InvalidSystemError("expected System")
    options = options or ReductionOptions()
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    if options.coordinate_search:
        if candidates is not None:
            raise ValueError("use an explicit chart to select transformed candidates")
        from equireduce.search import search_coordinates

        return search_coordinates(system, options=options, proof=proof, lean=lean)
    method = (
        _core.reduce_affine_system
        if options.allow_blocks
        else _core.reduce_affine_singletons
    )
    core = method(system, candidates=None if candidates is None else tuple(candidates))
    inherited_domain = tuple(
        value.subs(dict(core.reconstruction), simultaneous=True)
        for value in system.conditions
    )
    core = replace(core, conditions=_canonical((*core.conditions, *inherited_domain)))
    result = _from_core(system, core)
    if proof != "none":
        from equireduce.lean import attach_proof

        result = attach_proof(result, proof=proof, config=lean)
    return result


def _from_core(system: System, core: _core.ReductionResult) -> ReductionResult:
    """Rebuild a public result from data, without rerunning elimination."""
    certificate = Certificate(system, core)
    check = verify_certificate(system, certificate)
    if check.status is not _core.CertificateStatus.VERIFIED:
        raise CertificateError("; ".join((*check.failures, *check.unresolved)))
    reconstruction = dict(core.reconstruction)
    inherited = _canonical(
        value.subs(reconstruction, simultaneous=True) for value in system.conditions
    )
    additional = tuple(
        condition for condition in core.conditions if condition not in inherited
    )
    reduced = System.algebraic(
        core.reduced_residuals,
        core.reduced_unknowns,
        parameters=system.parameters,
        conditions=core.conditions,
        residual_names=tuple(
            system.residual_names[i] for i in core.reduced_residual_indices
        ),
    )
    result = ReductionResult(
        source=system,
        reduced_system=reduced,
        remaining_unknowns=core.reduced_unknowns,
        reconstruction=reconstruction,
        conditions=core.conditions,
        additional_conditions=additional,
        coverage="conditional" if additional else "complete",
        assumption_consistency=assumption_consistency(core.conditions),
        certificate=certificate,
        symbolic_check=check,
        metrics=measure(system, reduced, reconstruction),
        search={"complete": True, "stopping_reason": core.stopping_reason},
    )
    return result
