"""Bounded search over an explicitly declared finite family of affine charts."""

from __future__ import annotations

from dataclasses import dataclass, replace
from itertools import combinations, islice
from time import perf_counter

import sympy as sp

from equireduce.api import reduce_system
from equireduce.coordinates import AffineTransform, reduce_in_coordinates
from equireduce.errors import CertificateError
from equireduce.result import FormalCheck, ReductionOptions
from equireduce.system import System


@dataclass(frozen=True)
class CandidateSummary:
    matrix: sp.ImmutableMatrix
    score: tuple | None
    remaining_unknowns: int | None
    estimated_proof_operations: int | None
    error: str | None = None


@dataclass(frozen=True)
class SearchReport:
    source: System
    variables: tuple
    evaluated: tuple[CandidateSummary, ...]
    candidates_available: int
    candidates_evaluated: int
    complete: bool
    best_index: int
    budget: int
    coefficient_bound: int
    family: str = "integer-affine-and-shared-reference/v1"

    def __post_init__(self):
        size = len(self.source.unknowns)
        available = (
            1
            + size * (size - 1) * (2 * self.coefficient_bound + 1)
            + (size if size >= 3 else 0)
        )
        if type(self.budget) is not int or self.budget < 1:
            raise ValueError("search budget must be a positive integer")
        if self.candidates_available != available or self.candidates_evaluated != len(
            self.evaluated
        ):
            raise ValueError("search family/count mismatch")
        if self.complete != (len(self.evaluated) == available):
            raise ValueError("complete flag does not match the declared family")
        if len(self.evaluated) > min(self.budget, available):
            raise ValueError("search report exceeds its budget")
        if not 0 <= self.best_index < len(self.evaluated):
            raise ValueError("invalid selected candidate index")
        expected = islice(_matrices(size, self.coefficient_bound), len(self.evaluated))
        if any(
            entry.matrix != matrix
            for entry, matrix in zip(self.evaluated, expected, strict=True)
        ):
            raise ValueError("reported matrices are not the declared family prefix")


def _variables(source):
    occupied = {value.name for value in (*source.unknowns, *source.parameters)}
    result = []
    for index in range(len(source.unknowns)):
        name = f"coord_u{index}"
        while name in occupied:
            name += "_"
        occupied.add(name)
        result.append(sp.Symbol(name, real=True))
    return tuple(result)


def _matrices(size, bound):
    yield sp.ImmutableMatrix.eye(size)
    if size >= 3:
        for reference in range(size):
            matrix = sp.eye(size)
            for row in range(size):
                if row != reference:
                    matrix[row, reference] = 1
            yield sp.ImmutableMatrix(matrix)
    for left, right in combinations(range(size), 2):
        matrix = sp.eye(size)
        matrix.row_swap(left, right)
        yield sp.ImmutableMatrix(matrix)
    for left in range(size):
        for right in range(size):
            if left == right:
                continue
            for coefficient in range(-bound, bound + 1):
                if coefficient:
                    matrix = sp.eye(size)
                    matrix[left, right] = coefficient
                    yield sp.ImmutableMatrix(matrix)
    for left, right in combinations(range(size), 2):
        matrix = sp.eye(size)
        matrix[left, right], matrix[right, left], matrix[right, right] = 1, 1, -1
        yield sp.ImmutableMatrix(matrix)


def search_coordinates(source, *, options=None, proof="none", lean=None):
    """Select a checked chart within a budget; optimality is relative to this family."""
    if proof not in ("none", "generate", "require"):
        raise ValueError("unknown proof mode")
    options = options or ReductionOptions()
    inner_options = replace(options, coordinate_search=False)
    variables = _variables(source)
    size = len(variables)
    available = (
        1
        + size * (size - 1) * (2 * options.coefficient_bound + 1)
        + (size if size >= 3 else 0)
    )
    entries = []
    best, best_score, best_index = None, None, -1
    for index, matrix in enumerate(
        islice(_matrices(size, options.coefficient_bound), options.max_candidates)
    ):
        try:
            result = (
                reduce_in_coordinates(
                    source,
                    AffineTransform.create(source, variables=variables, matrix=matrix),
                    options=inner_options,
                )
                if size
                else reduce_system(source, options=inner_options)
            )
        except CertificateError as exc:
            entries.append(CandidateSummary(matrix, None, None, None, str(exc)))
            continue
        metrics = result.metrics
        score = (
            len(result.remaining_unknowns),
            metrics.reduced_jacobian_operations,
            metrics.reduced_operations,
            metrics.reduced_dag_nodes,
            len(result.additional_conditions),
            sum(abs(int(v)) for v in matrix),
            index,
        )
        entries.append(
            CandidateSummary(
                matrix,
                score,
                len(result.remaining_unknowns),
                metrics.estimated_proof_operations,
            )
        )
        if best_score is None or score < best_score:
            best, best_score, best_index = result, score, index
    if best is None:
        raise CertificateError("no candidate in the declared search budget verified")
    report = SearchReport(
        source,
        variables,
        tuple(entries),
        available,
        len(entries),
        len(entries) == available,
        best_index,
        options.max_candidates,
        options.coefficient_bound,
    )
    best = replace(best, search=report)
    if proof != "none":
        from equireduce.lean import attach_proof

        best = attach_proof(best, proof=proof, config=lean)
    return best


def _ranks(values):
    return [
        1
        + sum(other < value for other in values)
        + (sum(other == value for other in values) - 1) / 2
        for value in values
    ]


def _spearman(estimates, measurements):
    if len(estimates) < 2:
        return None
    left, right = _ranks(estimates), _ranks(measurements)
    mean = (len(left) + 1) / 2
    covariance = sum((a - mean) * (b - mean) for a, b in zip(left, right, strict=True))
    variance = sum((a - mean) ** 2 for a in left) * sum((b - mean) ** 2 for b in right)
    return covariance / variance**0.5 if variance else None


@dataclass(frozen=True)
class BenchmarkEntry:
    candidate_index: int
    estimated_operations: int
    seconds: float
    verification: FormalCheck


@dataclass(frozen=True)
class BenchmarkReport:
    entries: tuple[BenchmarkEntry, ...]
    candidates_available: int
    candidates_attempted: int
    complete: bool
    search_complete: bool
    spearman_correlation: float | None
    source_sha256: str

    def to_record(self):
        return {
            "schema": "equireduce.coordinate-benchmark/v1",
            "source_sha256": self.source_sha256,
            "candidates_available": self.candidates_available,
            "candidates_attempted": self.candidates_attempted,
            "complete": self.complete,
            "search_complete": self.search_complete,
            "spearman_correlation": self.spearman_correlation,
            "entries": [
                {
                    "candidate_index": entry.candidate_index,
                    "estimated_operations": entry.estimated_operations,
                    "seconds": entry.seconds,
                    "status": entry.verification.status.value,
                    "mathlib_revision": entry.verification.mathlib_revision,
                    "lean_version": entry.verification.toolchain_version,
                    "source_sha256": entry.verification.source_sha256,
                }
                for entry in self.entries
            ],
        }


def benchmark_coordinates(source, report: SearchReport, *, max_candidates=3, lean=None):
    """Measure generation plus real Lean verification for top-ranked search entries."""
    import hashlib

    from equireduce.artifacts import Codec, _canonical
    from equireduce.lean import verify_with_lean

    if source != report.source:
        raise ValueError("benchmark source differs from the search source")
    if type(max_candidates) is not int or max_candidates < 1:
        raise ValueError("max_candidates must be a positive integer")
    ranked = sorted(
        (
            (index, entry)
            for index, entry in enumerate(report.evaluated)
            if entry.score is not None
        ),
        key=lambda pair: pair[1].score or (),
    )
    entries = []
    for index, summary in ranked[:max_candidates]:
        candidate = (
            reduce_in_coordinates(
                source,
                AffineTransform.create(
                    source,
                    variables=report.variables,
                    matrix=summary.matrix,
                ),
            )
            if report.variables
            else reduce_system(source)
        )
        start = perf_counter()
        verification = verify_with_lean(source, candidate.certificate, config=lean)
        entries.append(
            BenchmarkEntry(
                index,
                candidate.metrics.estimated_proof_operations,
                perf_counter() - start,
                verification,
            )
        )
    verified = [
        entry for entry in entries if entry.verification.status.value == "verified"
    ]
    correlation = _spearman(
        [entry.estimated_operations for entry in verified],
        [entry.seconds for entry in verified],
    )
    digest = hashlib.sha256(_canonical(Codec().encode(source))).hexdigest()
    return BenchmarkReport(
        tuple(entries),
        len(ranked),
        len(entries),
        len(entries) == len(ranked),
        report.complete,
        correlation,
        digest,
    )
