"""Independent replay of implicit result fields, initial samples and search reports."""

from dataclasses import fields, replace

from equireduce.errors import ArtifactError, CertificateError, UnsupportedDomainError
from equireduce.implicit_reduction import (
    _from_implicit_certificate,
    reduce_implicit_dae,
)
from equireduce.provenance import verify_provenance
from equireduce.time_coordinates import (
    ImplicitCoordinateCertificate,
    _wrap_implicit_coordinate,
)


def initial_arguments(check):
    if check.time is None:
        return {}
    derived = dict(check.derived_values)
    missing = set(check.input_unknowns)
    return dict(
        initial_time=check.time,
        initial_values={k: v for k, v in check.values if k not in derived},
        initial_rates=dict(check.rates),
        parameter_values=dict(check.parameter_values),
        initial_input_values={k: v for k, v in check.input_values if v not in missing},
        initial_input_rates={k: v for k, v in check.input_rates if v not in missing},
    )


def replay_partition_report(result):
    report = result.search
    if report is None:
        return
    if len(report.evaluated) > 512:
        raise ArtifactError("partition replay exceeds limit")
    if (
        replace(
            result.source,
            differential=report.source.differential,
            algebraic=report.source.algebraic,
        )
        != report.source
    ):
        raise ArtifactError("partition report source mismatch")
    scores = []
    for index, entry in enumerate(report.evaluated):
        candidate = replace(
            report.source,
            algebraic=entry.algebraic,
            differential=tuple(
                v for v in report.source.unknowns if v not in entry.algebraic
            ),
        )
        try:
            replay = reduce_implicit_dae(candidate, max_minors=1)
        except (UnsupportedDomainError, CertificateError) as exc:
            if entry.score is not None or entry.error is None:
                raise ArtifactError("partition failure mismatch") from exc
            continue
        score = (
            len(replay.remaining_unknowns),
            len(replay.additional_conditions),
            sum(int(v.count_ops()) for v in replay.reduced_system.residuals),
            index,
        )
        if score != entry.score or entry.error is not None:
            raise ArtifactError("partition score mismatch")
        scores.append((score, index))
    if (
        not scores
        or min(scores)[1] != report.best_index
        or report.evaluated[report.best_index].algebraic != result.source.algebraic
    ):
        raise ArtifactError("selected partition does not match result")


def replay_implicit_result(result):
    certificate = result.certificate
    budget = result.structure.rank.max_minors if result.structure.rank else 64
    if budget > 4096:
        raise ArtifactError("rank replay budget exceeds limit")
    initial = initial_arguments(result.initial_check)
    if isinstance(certificate, ImplicitCoordinateCertificate):
        inner = _from_implicit_certificate(
            certificate.inner, max_minors=budget, **initial
        )
        expected = _wrap_implicit_coordinate(certificate, inner)
    else:
        expected = _from_implicit_certificate(certificate, max_minors=budget, **initial)
    for descriptor in fields(result):
        if descriptor.name in (
            "symbolic_check",
            "formal_check",
            "search",
            "provenance",
        ):
            continue
        if getattr(result, descriptor.name) != getattr(expected, descriptor.name):
            raise ArtifactError(
                f"implicit {descriptor.name} does not match certificate"
            )
    replay_partition_report(result)
    verify_provenance(result.source, result.provenance)
    return replace(result, symbolic_check=expected.symbolic_check)
