"""Exact first-order implicit DAE inputs, with an explicit manual partition."""

from __future__ import annotations

from dataclasses import dataclass

import sympy as sp
from sympy.core.relational import Relational

from equireduce.conditions import (
    domain_conditions,
    intrinsic_conditions,
    normalize_conditions,
    validate_condition,
)
from equireduce.dae import _exact_expression
from equireduce.errors import InvalidSystemError, UnsupportedDomainError
from equireduce.smooth import SmoothFunction, branch_data, raw_replace
from equireduce.system import System


def substitute_condition(condition, mapping):
    """Transport a predicate without letting assumptions erase its explicit domain."""
    if isinstance(condition, Relational):
        return condition.func(
            condition.lhs.xreplace(mapping),
            condition.rhs.xreplace(mapping),
            evaluate=False,
        )
    if isinstance(condition, (sp.And, sp.Or, sp.Not)):
        return condition.func(
            *(substitute_condition(v, mapping) for v in condition.args), evaluate=False
        )
    return condition.xreplace(mapping)


def _real_time_function(value, time):
    return (
        isinstance(value, sp.core.function.AppliedUndef)
        and value.args == (time,)
        and value.is_real is True
        and value.is_commutative is True
    )


@dataclass(frozen=True)
class ImplicitDAESystem:
    """A source snapshot of ``F(t, X, X', p, u, u') = 0`` on an open interval.

    ``differential`` and ``algebraic`` are a requested partition, not a claim
    about the rank, index, independence of states or existence of solutions.
    Singular mass matrices and rectangular systems remain valid inputs.
    """

    time: sp.Symbol
    unknowns: tuple
    differential: tuple
    algebraic: tuple
    residuals: tuple
    interval: tuple
    parameters: tuple = ()
    inputs: tuple = ()
    conditions: tuple = ()
    residual_names: tuple = ()
    regularity: str = "differentiable_on_open_interval"
    smooth_functions: tuple = ()
    branch_choices: tuple = ()

    @property
    def domain(self):
        return "time"

    @property
    def interval_condition(self):
        return sp.Lt(*self.interval)

    @property
    def input_regularity(self):
        """Declaring an input assumes its differentiability on this interval."""
        return tuple((value, self.regularity) for value in self.inputs)

    @property
    def slot_map(self):
        """Deterministic temporary real coordinates, never a trajectory claim."""
        occupied = {v.name for v in (self.time, *self.parameters)}
        mapping = {}
        for prefix, values in (
            ("dae_state", self.unknowns),
            ("dae_input", self.inputs),
        ):
            for index, value in enumerate(values):
                name = f"{prefix}_{index}"
                while name in occupied:
                    name += "_"
                occupied.add(name)
                mapping[value] = sp.Symbol(name, real=True)
        return mapping

    @property
    def rate_map(self):
        occupied = {
            v.name for v in (*self.slot_map.values(), self.time, *self.parameters)
        }
        mapping = {}
        for index, value in enumerate((*self.unknowns, *self.inputs)):
            name = f"dae_rate_{index}"
            while name in occupied:
                name += "_"
            occupied.add(name)
            mapping[sp.Derivative(value, self.time)] = sp.Symbol(name, real=True)
        return mapping

    def __post_init__(self):
        for name in (
            "unknowns",
            "differential",
            "algebraic",
            "residuals",
            "interval",
            "parameters",
            "inputs",
            "conditions",
            "residual_names",
            "smooth_functions",
            "branch_choices",
        ):
            object.__setattr__(self, name, tuple(getattr(self, name)))
        if not isinstance(self.time, sp.Symbol) or self.time.is_real is not True:
            raise InvalidSystemError("time must be a real Symbol")
        if self.regularity != "differentiable_on_open_interval":
            raise UnsupportedDomainError(
                "only differentiable open-interval trajectories are supported"
            )
        if self.time in self.parameters:
            raise InvalidSystemError("time is not a constant parameter")
        System.algebraic((), (), parameters=self.parameters)
        functions = (*self.unknowns, *self.inputs)
        if any(not isinstance(v, SmoothFunction) for v in self.smooth_functions):
            raise InvalidSystemError(
                "smooth_functions must contain SmoothFunction declarations"
            )
        declared = tuple(
            f for v in self.smooth_functions for f in (v.function, *v.partials)
        )
        if len(set(declared)) != len(declared) or set(declared) & {
            v.func for v in functions
        }:
            raise InvalidSystemError(
                "smooth function and partial names must be distinct"
            )
        if len(set(functions)) != len(functions):
            raise InvalidSystemError("states and inputs must be unique and disjoint")
        if any(not _real_time_function(v, self.time) for v in functions):
            raise InvalidSystemError(
                "states and inputs must be declared real functions of time"
            )
        partition = self.differential + self.algebraic
        if len(set(partition)) != len(partition) or set(partition) != set(
            self.unknowns
        ):
            raise InvalidSystemError(
                "differential and algebraic variables must partition unknowns"
            )
        if len(self.interval) != 2:
            raise InvalidSystemError("open interval needs two exact endpoints")
        endpoints = tuple(_exact_expression(v) for v in self.interval)
        System.algebraic(endpoints, (), parameters=self.parameters)
        if sp.Lt(*endpoints) is sp.false:
            raise InvalidSystemError("open interval must be nonempty")
        object.__setattr__(self, "interval", endpoints)
        rows = tuple(sp.Integer(v) if type(v) is int else v for v in self.residuals)
        if any(not isinstance(v, sp.Expr) for v in rows):
            raise InvalidSystemError("residuals must be exact SymPy expressions")
        for row in rows:
            if row.has(sp.Float, sp.nan, sp.zoo, sp.oo, -sp.oo, sp.I):
                raise InvalidSystemError(
                    "all raw branches must be exact finite real expressions"
                )
            if not row.free_symbols <= {self.time, *self.parameters}:
                raise InvalidSystemError("raw branch contains undeclared symbols")
            for applied in row.atoms(sp.core.function.AppliedUndef):
                if (
                    applied.args == (self.time,)
                    and applied not in functions
                    and applied.func not in declared
                ):
                    raise InvalidSystemError(f"undeclared time input: {applied}")
            for rate in row.atoms(sp.Derivative):
                if rate.variable_count != ((self.time, 1),) or rate.expr.has(
                    sp.Derivative
                ):
                    raise UnsupportedDomainError(
                        "raw branches require first-order derivatives"
                    )
        if any(not validate_condition(v) for v in self.conditions):
            raise InvalidSystemError("conditions must be Boolean SymPy predicates")
        guards = normalize_conditions(self.conditions)
        branches, branch_guards = branch_data((*rows, *guards), self.branch_choices)
        selected = tuple(raw_replace(v, branches) for v in rows)
        guards = normalize_conditions((*guards, *branch_guards))
        expressions = (*selected, *(raw_replace(v, branches) for v in guards))
        for expression in expressions:
            if expression.has(
                sp.Abs,
                sp.sign,
                sp.Heaviside,
                sp.DiracDelta,
                sp.floor,
                sp.ceiling,
                sp.Min,
                sp.Max,
            ):
                raise UnsupportedDomainError(
                    "nonsmooth or piecewise DAE input needs an explicit smooth branch"
                )
            for applied in expression.atoms(sp.core.function.AppliedUndef):
                if applied.func in declared:
                    law = next(
                        (
                            v
                            for v in self.smooth_functions
                            if applied.func in (v.function, *v.partials)
                        ),
                        None,
                    )
                    if law is None or len(applied.args) != law.arity:
                        raise InvalidSystemError("smooth law arity mismatch")
                elif applied.args == (self.time,) and applied not in functions:
                    raise InvalidSystemError(f"undeclared time input: {applied}")
            for derivative in expression.atoms(sp.Derivative):
                if derivative.variable_count != (
                    (self.time, 1),
                ) or derivative.expr.has(sp.Derivative):
                    raise UnsupportedDomainError(
                        "only first derivatives with respect to the "
                        "declared time are supported"
                    )
        # Preserve original partial-operation domains before xreplace can cancel.
        guards = normalize_conditions(
            (
                *guards,
                *domain_conditions(expressions),
                *intrinsic_conditions(functions, expressions),
            )
        )
        mapping = dict(self.slot_map)
        occupied = {v.name for v in (*mapping.values(), self.time, *self.parameters)}
        derivatives = set().union(
            *(v.atoms(sp.Derivative) for v in (*selected, *guards))
        )
        for index, derivative in enumerate(sorted(derivatives, key=sp.srepr)):
            name = f"dae_raw_rate_{index}"
            while name in occupied:
                name += "_"
            occupied.add(name)
            mapping[derivative] = sp.Symbol(name, real=True)
        checked = System.algebraic(
            tuple(v.xreplace(mapping) for v in selected),
            tuple(mapping.values()),
            parameters=(self.time, *self.parameters),
            conditions=tuple(v.xreplace(mapping) for v in guards),
            residual_names=self.residual_names,
        )
        reverse = {v: k for k, v in mapping.items()}
        object.__setattr__(self, "residuals", rows)
        object.__setattr__(
            self,
            "conditions",
            normalize_conditions(
                substitute_condition(v, reverse) for v in checked.conditions
            ),
        )
        object.__setattr__(self, "residual_names", checked.residual_names)

    @classmethod
    def create(
        cls,
        *,
        time,
        unknowns,
        differential,
        algebraic,
        residuals,
        interval,
        parameters=(),
        inputs=(),
        conditions=(),
        residual_names=(),
        smooth_functions=(),
        branch_choices=(),
    ):
        return cls(
            time,
            unknowns,
            differential,
            algebraic,
            residuals,
            interval,
            parameters,
            inputs,
            conditions,
            residual_names,
            smooth_functions=tuple(smooth_functions),
            branch_choices=tuple(branch_choices),
        )
