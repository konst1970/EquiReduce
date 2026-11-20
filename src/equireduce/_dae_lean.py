"""Lift an algebraic certificate to actual differentiable trajectories."""

import sympy as sp

from equireduce._lean_export import (
    _conjunction,
    _LeanExpressionPrinter,
    proof_expressions,
)
from equireduce.errors import UnsupportedExpressionError


def _tuple(names):
    return (
        "⟨" + ", ".join(names) + "⟩"
        if len(names) > 1
        else names[0]
        if names
        else "True.intro"
    )


def _unpack(lines, hypothesis, names, indent="    "):
    if len(names) > 1:
        lines.append(indent + f"rcases {hypothesis} with ⟨" + ", ".join(names) + "⟩")
    elif names:
        lines.append(indent + f"have {names[0]} := {hypothesis}")


def generate_dae_lean(certificate):
    from equireduce.lean import generate_lean

    source = certificate.source
    algebraic = certificate.algebraic
    core = algebraic.reduction
    helper_expressions = proof_expressions(core)
    helper_printer = _LeanExpressionPrinter(helper_expressions, core.source_unknowns)
    helper = (
        generate_lean(algebraic.source, algebraic)
        .replace("theorem reduction_equivalence", "theorem algebraic_equivalence")
        .replace("#print axioms reduction_equivalence", "")
    )
    helper = (
        "import Mathlib.Analysis.Calculus.Deriv.Pow\n"
        "import Mathlib.Analysis.Calculus.Deriv.Add\n"
        "import Mathlib.Analysis.Calculus.Deriv.Inv\n"
        "import Mathlib.Tactic.Convert\n" + helper
    )
    slots = source.slot_map
    xs = tuple(slots[v] for v in source.differential)
    ys = tuple(slots[v] for v in source.algebraic)
    occupied = {str(v) for v in (source.time, *source.parameters, *slots.values())}
    velocities = []
    for index in range(len(xs)):
        name = f"dae_velocity_{index}"
        while name in occupied:
            name += "_"
        occupied.add(name)
        velocities.append(sp.Symbol(name, real=True))
    reconstruction = tuple(
        value.xreplace(slots) for _, value in certificate.reconstruction
    )
    rhs = tuple(value.xreplace(slots) for value in source.rhs)
    reduced_rhs = tuple(value.xreplace(slots) for value in certificate.reduced_rhs)
    rates = {
        sp.diff(v, source.time): r
        for v, r in zip(source.differential, velocities, strict=True)
    }
    derivatives = tuple(
        value.xreplace(rates).xreplace(slots)
        for _, value in certificate.reconstruction_derivatives
    )
    conditions = tuple(value.xreplace(slots) for value in certificate.conditions)
    expressions = (
        *helper_expressions,
        *rhs,
        *reduced_rhs,
        *reconstruction,
        *derivatives,
        *conditions,
        *source.interval,
    )
    for expression in expressions:
        for node in sp.preorder_traversal(expression):
            if isinstance(node, sp.Function) and not isinstance(
                node, sp.core.function.AppliedUndef
            ):
                raise UnsupportedExpressionError(
                    f"DAE Lean export does not support {node.func}"
                )
    printer = _LeanExpressionPrinter(
        expressions, (*slots.values(), source.time, *source.parameters, *velocities)
    )
    render = printer.print
    prefix = "er_"
    allocated = (*printer.symbol_names.values(), *printer.function_names.values())
    while any(name.startswith(prefix) for name in allocated):
        prefix += "_"
    clock, sample = prefix + "time", prefix + "sample"
    lower, upper = map(render, source.interval)
    membership = f"{clock} ∈ Set.Ioo ({lower}) ({upper})"
    trajectories = {v: prefix + f"X{i}" for i, v in enumerate(xs)}
    trajectories.update({v: prefix + f"Y{i}" for i, v in enumerate(ys)})

    def at(name):
        return {
            source.time: name,
            **{v: f"({f} {name})" for v, f in trajectories.items()},
        }

    current, nearby = at(clock), at(sample)
    function_binders = [
        f"({printer.function_names[f]} : " + " → ".join(["ℝ"] * (arity + 1)) + ")"
        for f, arity in sorted(
            printer.function_arities.items(),
            key=lambda pair: printer.function_names[pair[0]],
        )
    ]
    common = [f"({printer.symbol(v)} : ℝ)" for v in source.parameters]
    common += [f"({trajectories[v]} : ℝ → ℝ)" for v in xs]
    common += function_binders
    guard_names = [f"hDomain{i}" for i in range(len(conditions))]
    point_guards = [
        f"({name} : {render(condition, current)})"
        for name, condition in zip(guard_names, conditions, strict=True)
    ]

    # Independently prove the full symbolic chain rule for each reconstructed state.
    chain_binders = [*common, f"({clock} : ℝ)"]
    chain_binders += [f"({printer.symbol(v)} : ℝ)" for v in velocities]
    chain_binders += [
        f"(hRate{i} : HasDerivAt {trajectories[v]} {printer.symbol(r)} {clock})"
        for i, (v, r) in enumerate(zip(xs, velocities, strict=True))
    ]
    chain_binders += point_guards
    chain_props = [
        f"HasDerivAt (fun {sample} : ℝ => {render(phi, nearby)}) "
        f"({render(rate, current)}) {clock}"
        for phi, rate in zip(reconstruction, derivatives, strict=True)
    ]
    lines = [
        helper,
        "theorem reconstruction_chain_rule " + " ".join(chain_binders) + " :",
        "    " + _conjunction(chain_props) + " := by",
        "  classical",
    ]
    from equireduce._lean_calculus import rational_derivative_proofs

    calculations, chain_proofs = rational_derivative_proofs(
        reconstruction,
        time=source.time,
        xs=xs,
        velocities=velocities,
        render=render,
        current=current,
        nearby=nearby,
        clock=clock,
        sample=sample,
        guard_names=guard_names,
    )
    lines.extend(calculations)
    lines.append("  exact " + _tuple(chain_proofs))

    # Lift the pointwise algebraic iff to all times of the declared open interval.
    domain_prop = _conjunction([render(c, current) for c in conditions])
    outer = [
        *common,
        *(f"({trajectories[v]} : ℝ → ℝ)" for v in ys),
        f"(hInterval : ({lower}) < ({upper}))",
        f"(hDomain : ∀ {clock} : ℝ, {membership} → ({domain_prop}))",
    ]
    original_diff = _conjunction(
        [
            f"HasDerivAt {trajectories[v]} ({render(f, current)}) {clock}"
            for v, f in zip(xs, rhs, strict=True)
        ]
    )
    original_alg = _conjunction(
        [f"({render(row, current)} = 0)" for row in core.source_residuals]
    )
    regularity = _conjunction(
        [f"DifferentiableAt ℝ {trajectories[v]} {clock}" for v in ys]
    )
    reduced_diff = _conjunction(
        [
            f"HasDerivAt {trajectories[v]} ({render(f, current)}) {clock}"
            for v, f in zip(xs, reduced_rhs, strict=True)
        ]
    )
    graph = _conjunction(
        [
            f"({render(v, current)} = {render(phi, current)})"
            for v, phi in zip(ys, reconstruction, strict=True)
        ]
    )
    graph_assumption = f"(hGraph : ∀ {clock} : ℝ, {membership} → ({graph}))"
    rate_binders = [
        *chain_binders,
        *(f"({trajectories[v]} : ℝ → ℝ)" for v in ys),
        graph_assumption,
        f"(hTime : {membership})",
    ]
    actual_rate_props = [
        f"HasDerivAt {trajectories[v]} ({render(rate, current)}) {clock}"
        for v, rate in zip(ys, derivatives, strict=True)
    ]
    base_args = [printer.symbol(v) for v in source.parameters]
    base_args += [trajectories[v] for v in xs]
    base_args += [
        printer.function_names[f]
        for f in sorted(printer.function_arities, key=printer.function_names.get)
    ]

    def chain_application(rate_values, rate_proofs):
        return (
            "(reconstruction_chain_rule "
            + " ".join(
                f"({arg})"
                for arg in [*base_args, clock, *rate_values, *rate_proofs, *guard_names]
            )
            + ")"
        )

    lines += [
        "theorem reconstructed_rate_equivalence " + " ".join(rate_binders) + " :",
        "    " + _conjunction(actual_rate_props) + " := by",
        "  classical",
        "  have hChains := "
        + chain_application(
            [printer.symbol(v) for v in velocities],
            [f"hRate{i}" for i in range(len(xs))],
        ),
    ]
    chain_names = [f"hReconstructedRate{i}" for i in range(len(ys))]
    _unpack(lines, "hChains", chain_names, "  ")
    actual_names = []
    for index in range(len(ys)):
        name = f"hActual{index}"
        actual_names.append(name)
        lines += [
            f"  have {name} : {actual_rate_props[index]} := by",
            f"    apply {chain_names[index]}.congr_of_eventuallyEq",
            "    filter_upwards [Ioo_mem_nhds hTime.1 hTime.2] with "
            + sample
            + " hNear",
            f"    have hNearGraph := hGraph {sample} hNear",
        ]
        near_names = [f"hNearRec{i}" for i in range(len(ys))]
        _unpack(lines, "hNearGraph", near_names)
        lines.append(f"    exact {near_names[index]}")
    lines.append("  exact " + _tuple(actual_names))
    lines += [
        "theorem reduction_equivalence " + " ".join(outer) + " :",
        f"    (∀ {clock} : ℝ, {membership} → (({original_diff}) ∧ "
        f"({original_alg}) ∧ ({regularity}))) ↔",
        f"    ((∀ {clock} : ℝ, {membership} → ({reduced_diff})) ∧",
        f"     (∀ {clock} : ℝ, {membership} → ({graph}))) := by",
        "  classical",
        "  constructor",
        "  · intro hSource",
        "    constructor",
        f"    · intro {clock} hTime",
        f"      rcases hSource {clock} hTime with ⟨hDiff, hAlg, hReg⟩",
    ]
    helper_symbols = set(core.source_unknowns)
    for expression in helper_expressions:
        helper_symbols.update(expression.free_symbols)
    helper_order = list(core.source_unknowns) + sorted(
        helper_symbols - set(core.source_unknowns), key=lambda v: (str(v), sp.srepr(v))
    )
    helper_functions = sorted(
        helper_printer.function_arities, key=helper_printer.function_names.get
    )
    helper_args = (
        [render(v, current) for v in helper_order]
        + [printer.function_names[f] for f in helper_functions]
        + guard_names
    )
    application = (
        "(algebraic_equivalence " + " ".join(f"({a})" for a in helper_args) + ")"
    )
    rec_names = [f"hRec{i}" for i in range(len(ys))]
    rec_simp = ", ".join(rec_names)

    def setup(indent):
        lines.append(indent + f"have hGuards := hDomain {clock} hTime")
        _unpack(lines, "hGuards", guard_names, indent)

    setup("      ")
    lines.append(f"      have hGraph := ({application}.mp hAlg).2")
    _unpack(lines, "hGraph", rec_names, "      ")
    lines += [
        f"      convert hDiff using 1 <;> simp only [{rec_simp}] <;> ring_nf",
        f"    · intro {clock} hTime",
        f"      rcases hSource {clock} hTime with ⟨hDiff, hAlg, hReg⟩",
    ]
    setup("      ")
    lines += [
        f"      exact ({application}.mp hAlg).2",
        "  · rintro ⟨hDiff, hGraph⟩",
        f"    intro {clock} hTime",
        f"    have hDeriv := hDiff {clock} hTime",
        f"    have hRec := hGraph {clock} hTime",
    ]
    _unpack(lines, "hRec", rec_names)
    setup("    ")
    lines += [
        "    refine ⟨?_, ?_, ?_⟩",
        f"    · convert hDeriv using 1 <;> simp only [{rec_simp}] <;> ring_nf",
        "    · exact " + application + ".mpr ⟨True.intro, " + _tuple(rec_names) + "⟩",
    ]
    rates_names = [f"hActualRate{i}" for i in range(len(xs))]
    _unpack(lines, "hDeriv", rates_names)
    rate_args = [
        *base_args,
        clock,
        *(render(v, current) for v in reduced_rhs),
        *rates_names,
        *guard_names,
        *(trajectories[v] for v in ys),
        "hGraph",
        "hTime",
    ]
    rate_app = (
        "(reconstructed_rate_equivalence "
        + " ".join(f"({arg})" for arg in rate_args)
        + ")"
    )
    lines.append("    · have hChains := " + rate_app)
    chain_names = [f"hReconstructedRate{i}" for i in range(len(ys))]
    _unpack(lines, "hChains", chain_names, "      ")
    reg_names = []
    for index, variable in enumerate(ys):
        name = f"hRegular{index}"
        reg_names.append(name)
        lines += [
            f"      have {name} : DifferentiableAt ℝ "
            f"{trajectories[variable]} {clock} :=",
            f"        {chain_names[index]}.differentiableAt",
        ]
    lines += [
        "      exact " + _tuple(reg_names),
        "#print axioms reconstruction_chain_rule",
        "#print axioms reduction_equivalence",
    ]
    return "\n".join(lines) + "\n"
