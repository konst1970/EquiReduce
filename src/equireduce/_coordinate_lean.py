"""One Lean theorem composing an affine chart with an elimination trace."""

import sympy as sp

from equireduce._lean_export import (
    _conjunction,
    _LeanExpressionPrinter,
    _nonzero_factors,
    proof_expressions,
)
from equireduce.conditions import simplify_condition
from equireduce.coordinates import augmented_certificate


def _proof_tuple(names):
    return (
        "⟨" + ", ".join(names) + "⟩"
        if len(names) > 1
        else names[0]
        if names
        else "True.intro"
    )


def generate_coordinate_lean(certificate):
    from equireduce.lean import generate_lean

    augmented = augmented_certificate(certificate)
    core = augmented.reduction
    helper = (
        generate_lean(augmented.source, augmented)
        .replace("theorem reduction_equivalence", "theorem augmented_equivalence")
        .replace("#print axioms reduction_equivalence", "")
    )
    expressions = proof_expressions(core)
    printer = _LeanExpressionPrinter(expressions, core.source_unknowns)
    render = printer.print
    symbols = set(core.source_unknowns)
    for expression in expressions:
        symbols.update(expression.free_symbols)
    order = list(core.source_unknowns) + sorted(
        symbols - set(core.source_unknowns),
        key=lambda item: (str(item), sp.srepr(item)),
    )
    functions = sorted(printer.function_arities, key=printer.function_names.get)
    conditions = []
    for condition in core.conditions:
        simplified = simplify_condition(condition)
        if simplified is not sp.true:
            condition = simplified
        if condition is not sp.true and condition not in conditions:
            conditions.append(condition)
    transform = certificate.transform
    variables = transform.variables
    inverse = {variable: render(value) for variable, value in transform.inverse_map}
    binders = [f"({printer.symbol(v)} : ℝ)" for v in order if v not in variables]
    binders += [
        f"({printer.function_names[f]} : "
        + " → ".join(["ℝ"] * (printer.function_arities[f] + 1))
        + ")"
        for f in functions
    ]
    guard_names = [f"hOuter{i}" for i in range(len(conditions))]
    binders += [
        f"({name} : {render(condition, inverse)})"
        for name, condition in zip(guard_names, conditions, strict=True)
    ]
    original_prop = _conjunction(
        [f"({render(row)} = 0)" for row in certificate.source.residuals]
    )
    reduced_prop = _conjunction(
        [f"({render(row)} = 0)" for row in core.reduced_residuals]
    )
    reconstruction_prop = _conjunction(
        [f"({printer.symbol(v)} = {render(value)})" for v, value in core.reconstruction]
    )
    domain_prop = _conjunction([render(value) for value in conditions])
    native_target = f"(({reduced_prop}) ∧ ({reconstruction_prop}))"
    target = f"(({domain_prop}) ∧ {native_target})"
    for variable in reversed(variables):
        target = f"∃ ({printer.symbol(variable)} : ℝ), {target}"

    def application(substitutions, guards):
        arguments = [substitutions.get(v, printer.symbol(v)) for v in order]
        arguments += [printer.function_names[f] for f in functions]
        arguments += guards
        return (
            "(augmented_equivalence " + " ".join(f"({arg})" for arg in arguments) + ")"
        )

    lines = [
        helper,
        "theorem reduction_equivalence " + " ".join(binders) + " :",
        f"    ({original_prop}) ↔ ({target}) := by",
        "  classical",
    ]
    denominator_names: list[str] = []
    for denominator in dict.fromkeys(
        sp.together(value).as_numer_denom()[1] for _, value in transform.inverse_map
    ):
        if denominator.is_number:
            continue
        for condition, hypothesis in zip(conditions, guard_names, strict=True):
            if isinstance(condition, sp.Unequality) and _nonzero_factors(
                denominator
            ) == _nonzero_factors(condition.lhs - condition.rhs):
                name = f"hOuterDen{len(denominator_names)}"
                lines += [
                    f"  have {name} : {render(denominator)} ≠ 0 := by",
                    "    intro hZero",
                    f"    apply {hypothesis}",
                    "    nlinarith only [hZero]",
                ]
                denominator_names.append(name)
                break
    field_guards = guard_names + denominator_names
    lines += ["  constructor", "  · intro hSource"]
    original_count = len(certificate.source.residuals)
    if original_count > 1:
        lines.append(
            "    rcases hSource with ⟨"
            + ", ".join(f"hOriginal{i}" for i in range(original_count))
            + "⟩"
        )
    elif original_count:
        lines.append("    have hOriginal0 := hSource")
    for variable in variables:
        lines.append(f"    refine ⟨{inverse[variable]}, ?_⟩")
    lines += ["    refine ⟨?_, ?_⟩", "    · exact " + _proof_tuple(guard_names)]
    coordinate_proofs = []
    for index, equation in enumerate(augmented.source.residuals[original_count:]):
        name = f"hCoordinate{index}"
        coordinate_proofs.append(name)
        lines += (
            [
                f"    · have {name} : {render(equation, inverse)} = 0 := by",
                "        field_simp [" + ", ".join(field_guards) + "] <;> ring",
            ]
            if index == 0
            else [
                f"      have {name} : {render(equation, inverse)} = 0 := by",
                "        field_simp [" + ", ".join(field_guards) + "] <;> ring",
            ]
        )
    if not coordinate_proofs:
        lines.append("    ·")
    augmented_prop = _conjunction(
        [f"({render(row, inverse)} = 0)" for row in augmented.source.residuals]
    )
    source_names = [f"hOriginal{i}" for i in range(original_count)] + coordinate_proofs
    lines += [
        f"      have hAugmented : {augmented_prop} := " + _proof_tuple(source_names),
        "      exact " + application(inverse, guard_names) + ".mp hAugmented",
        "  · intro hTarget",
    ]
    for variable in variables:
        lines.append(f"    rcases hTarget with ⟨{printer.symbol(variable)}, hTarget⟩")
    lines.append("    rcases hTarget with ⟨hDomain, hReduced⟩")
    back_guards = [f"hBack{i}" for i in range(len(conditions))]
    if len(conditions) > 1:
        lines.append("    rcases hDomain with ⟨" + ", ".join(back_guards) + "⟩")
    elif conditions:
        lines.append("    have hBack0 := hDomain")
    lines.append(
        "    have hAugmented := " + application({}, back_guards) + ".mpr hReduced"
    )
    count = len(augmented.source.residuals)
    if count > 1:
        lines.append(
            "    rcases hAugmented with ⟨"
            + ", ".join(f"hRow{i}" for i in range(count))
            + "⟩"
        )
    elif count:
        lines.append("    have hRow0 := hAugmented")
    lines.append(
        "    exact " + _proof_tuple([f"hRow{i}" for i in range(original_count)])
    )
    lines.append("#print axioms reduction_equivalence")
    return "\n".join(lines) + "\n"
