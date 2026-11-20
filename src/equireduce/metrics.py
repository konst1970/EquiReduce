"""Deterministic expression metrics; these are not measured compiler times."""

from dataclasses import dataclass

import sympy as sp


@dataclass(frozen=True)
class ComplexityMetrics:
    source_unknowns: int
    reduced_unknowns: int
    source_operations: int
    reduced_operations: int
    source_jacobian_operations: int
    reduced_jacobian_operations: int
    reduced_dag_nodes: int
    estimated_proof_operations: int


def _jacobian_operations(system):
    if not system.residuals or not system.unknowns:
        return 0
    jacobian = sp.Matrix(system.residuals).jacobian(system.unknowns)
    return sum(int(sp.count_ops(value)) for value in jacobian)


def measure(source, reduced, reconstruction):
    before = sum(int(sp.count_ops(value)) for value in source.residuals)
    after = sum(int(sp.count_ops(value)) for value in reduced.residuals)
    dag = set()
    for value in reduced.residuals:
        dag.update(sp.preorder_traversal(value))
    reconstruction_cost = sum(
        int(sp.count_ops(value)) for value in reconstruction.values()
    )
    return ComplexityMetrics(
        len(source.unknowns),
        len(reduced.unknowns),
        before,
        after,
        _jacobian_operations(source),
        _jacobian_operations(reduced),
        len(dag),
        before + after + reconstruction_cost,
    )
