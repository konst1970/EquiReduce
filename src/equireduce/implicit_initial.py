"""Exact pointwise initial residual consistency, without numerical solving."""

from dataclasses import dataclass

import sympy as sp

from equireduce import _core
from equireduce.conditions import (
    domain_conditions,
    normalize_conditions,
    simplify_condition,
)
from equireduce.dae import _exact_expression
from equireduce.dae_structure import analyze_symbolic_rank
from equireduce.errors import InvalidSystemError


def resolve_initial_parameters(parameters):
    """Resolve exact, acyclic parameter assignments without iterative guessing."""
    pending = {k: _exact_expression(v) for k, v in parameters.items()}
    resolved: dict = {}
    while pending:
        ready = [
            k for k, v in pending.items() if not v.free_symbols.intersection(pending)
        ]
        if not ready:
            raise InvalidSystemError("cyclic initial parameter assignments")
        for key in ready:
            resolved[key] = pending.pop(key).xreplace(resolved)
        pending = {k: v.xreplace(resolved) for k, v in pending.items()}
    return resolved


@dataclass(frozen=True)
class ImplicitInitialCheck:
    status: str = "not_provided"
    time: sp.Expr | None = None
    values: tuple = ()
    derived_values: tuple = ()
    rates: tuple = ()
    parameter_values: tuple = ()
    obligations: tuple = ()
    rate_unknowns: tuple = ()
    rate_equations: tuple = ()
    rate_conditions: tuple = ()
    rate_witness: tuple = ()
    scope: str = "pointwise_residuals_and_reconstruction"
    trajectory_existence: str = "not_asserted"
    input_values: tuple = ()
    input_rates: tuple = ()
    input_unknowns: tuple = ()


def check_implicit_initial(
    result,
    *,
    initial_time=None,
    initial_values=None,
    initial_rates=None,
    parameter_values=None,
    initial_input_values=None,
    initial_input_rates=None,
):
    if all(
        v is None
        for v in (
            initial_time,
            initial_values,
            initial_rates,
            parameter_values,
            initial_input_values,
            initial_input_rates,
        )
    ):
        return ImplicitInitialCheck()
    if initial_time is None or initial_values is None:
        raise InvalidSystemError("initial time and values must be supplied together")
    source = result.source
    time = _exact_expression(initial_time)
    parameters = dict(parameter_values or {})
    provided = dict(initial_values)
    rates = dict(initial_rates or {})
    inputs = dict(initial_input_values or {})
    input_rates = dict(initial_input_rates or {})
    if not set(inputs) <= set(source.inputs) or not set(input_rates) <= {
        sp.Derivative(v, source.time) for v in source.inputs
    }:
        raise InvalidSystemError(
            "initial inputs/rates must use declared input functions/derivatives"
        )
    if not set(parameters) <= set(source.parameters) or not set(provided) <= set(
        source.unknowns
    ):
        raise InvalidSystemError("initial data uses undeclared states or parameters")
    if not set(result.remaining_unknowns) <= set(provided):
        raise InvalidSystemError("initial values must specify every retained state")
    allowed_rates = {sp.diff(v, source.time) for v in source.unknowns}
    if not set(rates) <= allowed_rates:
        raise InvalidSystemError(
            "initial rates must be declared first state derivatives"
        )
    for data in (parameters, provided, rates, inputs, input_rates):
        for key, value in tuple(data.items()):
            value = _exact_expression(value)
            if value.is_real is False or value.has(
                source.time, *source.unknowns, *source.inputs
            ):
                raise InvalidSystemError(
                    "initial expressions must be real and independent of states/time"
                )
            data[key] = value
    data_domains = domain_conditions(
        (
            time,
            *parameters.values(),
            *provided.values(),
            *rates.values(),
            *inputs.values(),
            *input_rates.values(),
        )
    )
    parameters = resolve_initial_parameters(parameters)
    time = time.xreplace(parameters)
    if time.is_real is False or time.has(source.time, *source.unknowns):
        raise InvalidSystemError(
            "initial time must be real and independent of states/time"
        )
    provided = {k: v.xreplace(parameters) for k, v in provided.items()}
    rates = {k: v.xreplace(parameters) for k, v in rates.items()}
    inputs = {k: v.xreplace(parameters) for k, v in inputs.items()}
    input_rates = {k: v.xreplace(parameters) for k, v in input_rates.items()}
    occupied = {v.name for v in (*source.parameters, source.time)}
    occupied.update(
        v.name
        for expression in (
            time,
            *parameters.values(),
            *provided.values(),
            *rates.values(),
            *inputs.values(),
            *input_rates.values(),
        )
        for v in expression.free_symbols
    )

    def fresh(name):
        while name in occupied:
            name += "_"
        occupied.add(name)
        return sp.Symbol(name, real=True)

    input_unknowns = []
    for i, value in enumerate(source.inputs):
        if value not in inputs:
            symbol = fresh(f"initial_input_{i}")
            inputs[value] = symbol
            input_unknowns.append(symbol)
    for i, derivative in enumerate(result.required_input_rates):
        if derivative not in input_rates:
            symbol = fresh(f"initial_input_rate_{i}")
            input_rates[derivative] = symbol
            input_unknowns.append(symbol)
    substitutions = {source.time: time, **parameters, **provided, **inputs}
    values = dict(provided)
    derived = {}
    for state, expression in result.reconstruction.items():
        value = sp.cancel(expression.xreplace(substitutions))
        if state not in values:
            values[state] = value
            derived[state] = value
    substitutions.update(values)
    obligations = [
        sp.Gt(time, source.interval[0].xreplace(parameters)),
        sp.Lt(time, source.interval[1].xreplace(parameters)),
        *(v.xreplace(parameters) for v in data_domains),
    ]
    for state, expression in result.reconstruction.items():
        obligations.append(sp.Eq(values[state], expression.xreplace(substitutions)))
    rate_map = {}
    for i, state in enumerate(source.unknowns):
        derivative = sp.diff(state, source.time)
        if derivative in rates:
            rate_map[derivative] = rates[derivative]
        else:
            rate_map[derivative] = fresh(f"initial_rate_{i}")
    unknowns = tuple(
        v
        for v in rate_map.values()
        if isinstance(v, sp.Symbol) and v not in rates.values()
    )
    rate_map.update(input_rates)
    # Eliminate unsupplied algebraic rates using the certified chain rule.
    for derivative, expression in result.reconstruction_derivatives.items():
        value = sp.cancel(expression.xreplace(rate_map).xreplace(substitutions))
        if derivative in rates:
            obligations.append(sp.Eq(rates[derivative], value))
        else:
            rate_map[derivative] = value
    unknowns = tuple(
        v for v in unknowns if any(value.has(v) for value in rate_map.values())
    )
    normalized = result.certificate.normalization
    rows = [
        sp.cancel(row.xreplace(rate_map).xreplace(substitutions))
        for row in normalized.residuals
    ]
    guards = [
        condition.xreplace(rate_map).xreplace(substitutions)
        for condition in normalized.conditions
    ]
    guards += [
        condition.xreplace(rate_map).xreplace(substitutions)
        for condition in result.conditions
    ]
    obligations += guards
    parameter_obligations: list = []
    rate_conditions: list = []
    for condition in obligations:
        condition = simplify_condition(condition)
        if condition is sp.false:
            raise InvalidSystemError(
                "incompatible initial values, rates or interval/domain"
            )
        if condition is sp.true:
            continue
        (
            rate_conditions
            if unknowns and condition.has(*unknowns)
            else parameter_obligations
        ).append(condition)
    equations = []
    for row in rows:
        zero_status = _core.symbolic_zero_status(row)
        if zero_status is _core.SymbolicZeroStatus.ZERO:
            continue
        if not unknowns or not row.has(*unknowns):
            condition = simplify_condition(sp.Eq(row, 0, evaluate=False))
            if condition is sp.false:
                raise InvalidSystemError("incompatible initial residual equations")
            if condition is not sp.true:
                parameter_obligations.append(condition)
        else:
            equations.append(row)
    # A missing rate is existential. Prove a witness only over the existing
    # parameter domain; never assume a new nonzero mass coefficient.
    witness = {v: sp.S.Zero for v in unknowns}

    def witness_valid(candidate):
        return all(
            _core.symbolic_zero_status(v.xreplace(candidate))
            is _core.SymbolicZeroStatus.ZERO
            for v in equations
        ) and all(
            simplify_condition(v.xreplace(candidate)) is sp.true
            for v in rate_conditions
        )

    if equations and unknowns and not witness_valid(witness):
        matrix, rhs = sp.linear_eq_to_matrix(equations, unknowns)
        rank = analyze_symbolic_rank(
            matrix,
            conditions=normalize_conditions((*guards, *parameter_obligations)),
            max_minors=128,
        )
        if rank.status == "exact" and rank.rank == matrix.rows:
            block = matrix[:, rank.pivot_columns]
            solution = block.inv(method="DM") * rhs
            witness = {v: sp.S.Zero for v in unknowns}
            witness.update(
                zip((unknowns[i] for i in rank.pivot_columns), solution, strict=True)
            )
        elif rank.upper_bound < matrix.rows:
            augmented_rank = analyze_symbolic_rank(
                matrix.row_join(rhs),
                conditions=normalize_conditions((*guards, *parameter_obligations)),
                max_minors=128,
            )
            if augmented_rank.lower_bound > rank.upper_bound:
                raise InvalidSystemError("incompatible initial rate equations")
    if witness_valid(witness):
        rate_equations = ()
        pending_rate_conditions = ()
        rate_witness = tuple(
            (derivative, sp.cancel(value.xreplace(witness)))
            for derivative, value in rate_map.items()
            if derivative not in input_rates
        )
    else:
        rate_equations = tuple(sp.Eq(v, 0, evaluate=False) for v in equations)
        pending_rate_conditions = tuple(rate_conditions)
        rate_witness = ()
    pending = normalize_conditions(parameter_obligations)
    status = (
        "conditional"
        if pending or rate_equations or pending_rate_conditions or input_unknowns
        else "verified"
    )
    return ImplicitInitialCheck(
        status,
        time,
        tuple(values.items()),
        tuple(derived.items()),
        tuple(rates.items()),
        tuple(parameters.items()),
        pending,
        unknowns,
        rate_equations,
        pending_rate_conditions,
        rate_witness,
        input_values=tuple(inputs.items()),
        input_rates=tuple(input_rates.items()),
        input_unknowns=tuple(input_unknowns),
    )
