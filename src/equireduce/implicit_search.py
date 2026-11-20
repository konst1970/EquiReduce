"""Deterministic bounded partition search; every selected block is certified."""

from dataclasses import dataclass, replace
from itertools import combinations, islice
from math import comb

import sympy as sp

from equireduce.dae_structure import normalize_implicit_dae
from equireduce.errors import (
    CertificateError,
    InvalidSystemError,
    UnsupportedDomainError,
)
from equireduce.implicit_initial import check_implicit_initial
from equireduce.implicit_reduction import reduce_implicit_dae


@dataclass(frozen=True)
class PartitionCandidate:
    algebraic: tuple
    score: tuple | None
    error: str | None = None


@dataclass(frozen=True)
class ImplicitPartitionReport:
    source: object
    preferred_differential: tuple
    candidates_available: int
    evaluated: tuple[PartitionCandidate, ...]
    complete: bool
    best_index: int
    budget: int
    family: str = "manual-partitions/derivative-free-rows-v1"

    @property
    def candidates_evaluated(self):
        return len(self.evaluated)

    def __post_init__(self):
        if (
            self.family != "manual-partitions/derivative-free-rows-v1"
            or type(self.complete) is not bool
            or type(self.best_index) is not int
        ):
            raise ValueError("invalid partition family or report types")
        pool, limit = _family(self.source, self.preferred_differential)
        available = sum(comb(len(pool), size) for size in range(limit + 1))
        if self.candidates_available != available or self.complete != (
            len(self.evaluated) == available
        ):
            raise ValueError("partition report family/completeness mismatch")
        if (
            type(self.budget) is not int
            or self.budget < 1
            or len(self.evaluated) > self.budget
        ):
            raise ValueError("invalid partition search budget")
        if not 0 <= self.best_index < len(self.evaluated):
            raise ValueError("invalid selected partition index")
        expected = tuple(islice(_partitions(pool, limit), len(self.evaluated)))
        if tuple(v.algebraic for v in self.evaluated) != expected:
            raise ValueError("partition report is not the declared family prefix")


def _family(source, preferred):
    normalized = normalize_implicit_dae(source)
    rows = [v for v in normalized.residuals if not v.has(sp.Derivative)]
    pool = tuple(
        v
        for v in source.unknowns
        if v not in preferred and any(row.has(v) for row in rows)
    )
    return pool, min(len(pool), len(rows))


def _partitions(pool, limit):
    yield ()
    for size in range(limit, 0, -1):
        yield from combinations(pool, size)


def search_implicit_partitions(
    source,
    *,
    max_candidates=32,
    preferred_differential=(),
    max_minors=64,
    proof="none",
    lean=None,
    initial_time=None,
    initial_values=None,
    initial_rates=None,
    parameter_values=None,
    initial_input_values=None,
    initial_input_rates=None,
):
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError("max_candidates must be a positive integer")
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    preferred = tuple(preferred_differential)
    if len(set(preferred)) != len(preferred) or not set(preferred) <= set(
        source.unknowns
    ):
        raise InvalidSystemError("preferred states must be distinct declared unknowns")
    pool, limit = _family(source, preferred)
    available = sum(comb(len(pool), size) for size in range(limit + 1))
    evaluations = []
    best = None
    best_score = None
    best_index = -1
    for index, algebraic in enumerate(islice(_partitions(pool, limit), max_candidates)):
        candidate = replace(
            source,
            differential=tuple(v for v in source.unknowns if v not in algebraic),
            algebraic=algebraic,
        )
        try:
            result = reduce_implicit_dae(candidate, max_minors=max_minors)
        except (UnsupportedDomainError, CertificateError) as exc:
            evaluations.append(PartitionCandidate(algebraic, None, str(exc)))
            continue
        score = (
            len(result.remaining_unknowns),
            len(result.additional_conditions),
            sum(int(sp.count_ops(v)) for v in result.reduced_system.residuals),
            index,
        )
        evaluations.append(PartitionCandidate(algebraic, score))
        if best_score is None or score < best_score:
            best, best_score, best_index = result, score, index
    if best is None:
        raise UnsupportedDomainError(
            "no partition in the declared budget reduced and verified"
        )
    report = ImplicitPartitionReport(
        source,
        preferred,
        available,
        tuple(evaluations),
        len(evaluations) == available,
        best_index,
        max_candidates,
    )
    best = replace(
        best,
        search=report,
        initial_check=check_implicit_initial(
            best,
            initial_time=initial_time,
            initial_values=initial_values,
            initial_rates=initial_rates,
            parameter_values=parameter_values,
            initial_input_values=initial_input_values,
            initial_input_rates=initial_input_rates,
        ),
    )
    if proof != "none":
        from equireduce.lean import attach_proof

        best = attach_proof(best, proof=proof, config=lean)
    return best
