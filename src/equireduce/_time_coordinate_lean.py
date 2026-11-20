"""Compose an invertible trajectory chart with the full implicit theorem."""

from copy import copy

import sympy as sp

from equireduce._dae_lean import _tuple, _unpack
from equireduce._implicit_lean import Context, _jet, generate_implicit_lean
from equireduce._lean_export import _conjunction
from equireduce.implicit import substitute_condition


def generate_time_coordinate_lean(certificate):
    transform = certificate.transform
    original = certificate.source
    inner = certificate.inner
    c = Context(inner)
    helper = (
        generate_implicit_lean(inner)
        .replace(
            "theorem reduction_equivalence", "theorem augmented_trajectory_equivalence"
        )
        .replace("#print axioms reduction_equivalence", "")
    )
    inverse = dict(transform.inverse_map)
    inverse_rates = dict(transform.inverse_rate_map)
    outer = copy(c)
    outer.conditions = tuple(
        _jet(
            substitute_condition(substitute_condition(v, inverse_rates), inverse),
            c.mapping,
            True,
        )
        for v in inner.conditions
    )
    outer.names = [f"hOuter{i}" for i in range(len(outer.conditions))]
    inverse_exprs = tuple(_jet(v, c.mapping, True) for _, v in transform.inverse_map)
    inverse_rate_exprs = tuple(
        _jet(v, c.mapping, True) for _, v in transform.inverse_rate_map
    )
    bodies = [c.printer.print(v, c.nearby) for v in inverse_exprs]
    functions = [f"(fun {c.sample} : ℝ => {v})" for v in bodies]
    new_slots = tuple(c.mapping[v] for v in transform.variables)
    inv_current = dict(c.current)
    for slot, body, rate in zip(new_slots, inverse_exprs, functions, strict=True):
        inv_current[slot] = c.printer.print(body, c.current)
        state = next(v for v in transform.variables if c.mapping[v] == slot)
        inv_current[c.mapping[sp.diff(state, original.time)]] = (
            f"(deriv {rate} {c.clock})"
        )

    def inverse_render(value):
        return c.printer.print(_jet(value, c.raw_mapping, True), inv_current)

    original_slots = tuple(c.mapping[v] for v in original.unknowns)
    common = [f"({c.printer.symbol(v)} : ℝ)" for v in original.parameters]
    common += [f"({c.trajectories[v]} : ℝ → ℝ)" for v in original_slots]
    common += [f"({c.trajectories[v]} : ℝ → ℝ)" for v in c.us]
    common += [
        f"({c.printer.function_names[f]} : "
        + " → ".join(["ℝ"] * (c.printer.function_arities[f] + 1))
        + ")"
        for f in c.functions
    ]
    common += c.smooth_binders
    projected_domain = _conjunction(
        [c.printer.print(v, c.current) for v in outer.conditions]
    )
    binders = [
        *common,
        f"(hInterval : ({c.render(original.interval[0])}) < "
        f"({c.render(original.interval[1])}))",
        *c.input_regularity_binders(),
        f"(hInverseDomain : ∀ {c.clock} : ℝ, {c.membership} → ({projected_domain}))",
    ]
    original_domain = _conjunction([c.render(v, True) for v in original.conditions])
    original_rows = _conjunction(
        [f"({c.render(v, True)} = 0)" for v in original.residuals]
    )
    domain = _conjunction([c.printer.print(v, c.current) for v in c.conditions])
    reduced_rows = _conjunction(
        [f"({c.render(v)} = 0)" for v in inner.reduced_residuals]
    )
    native_rhs = (
        f"((∀ {c.clock} : ℝ, {c.membership} → "
        f"(({c.diffs(c.retained)}) ∧ ({reduced_rows}))) ∧ "
        f"(∀ {c.clock} : ℝ, {c.membership} → ({c.graph()})))"
    )
    target = f"((∀ {c.clock} : ℝ, {c.membership} → ({domain})) ∧ {native_rhs})"
    for slot in reversed(new_slots):
        target = f"∃ ({c.trajectories[slot]} : ℝ → ℝ), {target}"
    lines = [
        helper,
        "theorem reduction_equivalence " + " ".join(binders) + " :",
        f"    (∀ {c.clock} : ℝ, {c.membership} → "
        f"(({c.diffs(original.unknowns)}) ∧ ({original_domain}) ∧ "
        f"({original_rows}))) ↔ ({target}) := by",
        "  classical",
        "  constructor",
        "  · intro hSource",
    ]
    inverse_props = [
        f"HasDerivAt {fn} ({c.printer.print(rate, c.current)}) {c.clock}"
        for fn, rate in zip(functions, inverse_rate_exprs, strict=True)
    ]
    lines += [
        f"    have hInverseRates : ∀ {c.clock} : ℝ, {c.membership} → ("
        + _conjunction(inverse_props)
        + ") := by",
        f"      intro {c.clock} hTime",
        f"      rcases hSource {c.clock} hTime with ⟨hDiff, hSDomain, hRows⟩",
        f"      have hOuter := hInverseDomain {c.clock} hTime",
    ]
    original_diff_names = [f"hOriginalDiff{i}" for i in range(len(original.unknowns))]
    _unpack(lines, "hDiff", original_diff_names, "      ")
    _unpack(lines, "hOuter", outer.names, "      ")
    for i, name in enumerate(original_diff_names):
        lines.append(f"      have hActualRate{i} := {name}.hasDerivAt")
    calculations, proofs = outer.calculate(inverse_exprs, "Inverse", outer.names)
    lines.extend("    " + line for line in calculations)
    inverse_has_names = []
    for i, proof in enumerate(proofs):
        name = f"hInverseHas{i}"
        inverse_has_names.append(name)
        lines += [
            f"      have {name} : {inverse_props[i]} := by",
            f"        refine ({proof}).congr_deriv ?_",
            "        (try field_simp [" + ", ".join(outer.names) + "]) <;> ring",
        ]
    lines.append("      exact " + _tuple(inverse_has_names))
    inverse_domain = _conjunction([inverse_render(v) for v in inner.conditions])
    lines += [
        f"    have hInnerDomain : ∀ {c.clock} : ℝ, "
        f"{c.membership} → ({inverse_domain}) := by",
        f"      intro {c.clock} hTime",
        f"      have hOuter := hInverseDomain {c.clock} hTime",
        f"      have hRates := hInverseRates {c.clock} hTime",
    ]
    _unpack(lines, "hRates", inverse_has_names, "      ")
    _unpack(lines, "hOuter", outer.names, "      ")
    inverse_equalities = []
    for i, name in enumerate(inverse_has_names):
        eq = f"hInverseRate{i}"
        inverse_equalities.append(eq)
        lines.append(f"      have {eq} := {name}.deriv")
    lines += [
        "      (try simp only ["
        + ", ".join(inverse_equalities)
        + "]) <;> convert "
        + _tuple(outer.names)
        + " using 1 <;> (try field_simp ["
        + ", ".join(outer.names)
        + "]) <;> (try ring_nf) <;> ring"
    ]
    # The chosen inverse trajectories satisfy the complete augmented MNA.
    all_diff = []
    for state in inner.source.unknowns:
        slot = c.mapping[state]
        fn = (
            c.trajectories[slot]
            if state in original.unknowns
            else functions[transform.variables.index(state)]
        )
        all_diff.append(f"DifferentiableAt ℝ {fn} {c.clock}")
    aug_domain = _conjunction([inverse_render(v) for v in inner.source.conditions])
    aug_rows = _conjunction(
        [f"({inverse_render(v)} = 0)" for v in inner.source.residuals]
    )
    lines += [
        f"    have hAugmented : ∀ {c.clock} : ℝ, {c.membership} → (("
        + _conjunction(all_diff)
        + f") ∧ ({aug_domain}) ∧ ({aug_rows})) := by",
        f"      intro {c.clock} hTime",
        f"      rcases hSource {c.clock} hTime with ⟨hDiff, hSDomain, hRows⟩",
        f"      have hOuter := hInverseDomain {c.clock} hTime",
        f"      have hRates := hInverseRates {c.clock} hTime",
    ]
    _unpack(lines, "hDiff", original_diff_names, "      ")
    _unpack(lines, "hOuter", outer.names, "      ")
    _unpack(lines, "hRates", inverse_has_names, "      ")
    source_domain_names = [
        f"hOriginalDomain{i}" for i in range(len(original.conditions))
    ]
    source_row_names = [f"hOriginalRow{i}" for i in range(len(original.residuals))]
    _unpack(lines, "hSDomain", source_domain_names, "      ")
    _unpack(lines, "hRows", source_row_names, "      ")
    aug_guards = []
    for i, condition in enumerate(inner.source.conditions):
        if condition in original.conditions:
            aug_guards.append(source_domain_names[original.conditions.index(condition)])
        else:
            name = f"hAugmentedDomain{i}"
            aug_guards.append(name)
            lines += [
                f"      have {name} : {inverse_render(condition)} := by",
                "        exact " + outer.guard(_jet(condition, c.mapping, True)),
            ]
    chart_names = []
    for i, row in enumerate(inner.source.residuals[len(original.residuals) :]):
        name = f"hChart{i}"
        chart_names.append(name)
        lines += [
            f"      have {name} : {inverse_render(row)} = 0 := by",
            "        (try field_simp ["
            + ", ".join(outer.names)
            + "]) <;> (try ring_nf) <;> ring",
        ]
    lines.append(
        "      exact ⟨"
        + _tuple(
            [
                *original_diff_names,
                *(f"{v}.differentiableAt" for v in inverse_has_names),
            ]
        )
        + ", "
        + _tuple(aug_guards)
        + ", "
        + _tuple([*source_row_names, *chart_names])
        + "⟩"
    )

    def application(forward):
        args = [c.printer.symbol(v) for v in original.parameters]
        for state in inner.source.unknowns:
            args.append(
                functions[transform.variables.index(state)]
                if forward and state in transform.variables
                else c.trajectories[c.mapping[state]]
            )
        args += [c.trajectories[v] for v in c.us]
        args += [c.printer.function_names[f] for f in c.functions]
        args += c.smooth_names
        args += ["hInterval"]
        if c.us:
            args.append("hInputRegularity")
        args.append("hInnerDomain")
        return (
            "(augmented_trajectory_equivalence "
            + " ".join(f"({v})" for v in args)
            + ")"
        )

    for fn in functions:
        lines.append(f"    refine ⟨{fn}, ?_⟩")
    lines += [
        "    exact ⟨hInnerDomain, " + application(True) + ".mp hAugmented⟩",
        "  · intro hTarget",
    ]
    for slot in new_slots:
        lines.append(f"    rcases hTarget with ⟨{c.trajectories[slot]}, hTarget⟩")
    lines += [
        "    rcases hTarget with ⟨hInnerDomain, hNative⟩",
        "    have hAugmented := " + application(False) + ".mpr hNative",
        f"    intro {c.clock} hTime",
        f"    rcases hAugmented {c.clock} hTime with ⟨hDiff, hDomain, hRows⟩",
    ]
    all_diff_names = [f"hAugDiff{i}" for i in range(len(inner.source.unknowns))]
    aug_domain_names = [f"hAugDomain{i}" for i in range(len(inner.source.conditions))]
    aug_row_names = [f"hAugRow{i}" for i in range(len(inner.source.residuals))]
    _unpack(lines, "hDiff", all_diff_names)
    _unpack(lines, "hDomain", aug_domain_names)
    _unpack(lines, "hRows", aug_row_names)
    lines.append(
        "    exact ⟨"
        + _tuple(all_diff_names[: len(original.unknowns)])
        + ", "
        + _tuple(
            [
                aug_domain_names[inner.source.conditions.index(v)]
                for v in original.conditions
            ]
        )
        + ", "
        + _tuple(aug_row_names[: len(original.residuals)])
        + "⟩"
    )
    lines.append("#print axioms reduction_equivalence")
    return "\n".join(lines) + "\n"
