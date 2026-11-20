"""Original implicit residuals ↔ reconstructed differentiable trajectories."""

from dataclasses import replace

import sympy as sp
from sympy.core.relational import Relational

from equireduce._dae_lean import _tuple, _unpack
from equireduce._lean_calculus import rational_derivative_proofs
from equireduce._lean_export import (
    _conjunction,
    _LeanExpressionPrinter,
    proof_expressions,
)
from equireduce.api import verify_certificate
from equireduce.conditions import domain_conditions, simplify_condition
from equireduce.errors import UnsupportedExpressionError
from equireduce.implicit import substitute_condition
from equireduce.result import Certificate
from equireduce.smooth import branch_data, raw_replace
from equireduce.system import System


def _jet(expression, mapping, preserve=False):
    if expression in mapping:
        return mapping[expression]
    if not expression.args:
        return expression
    args = tuple(_jet(v, mapping, preserve) for v in expression.args)
    if preserve and (isinstance(expression, (sp.Add, sp.Mul, sp.Pow, Relational))):
        return expression.func(*args, evaluate=False)
    return expression.func(*args)


class Context:
    def __init__(self, certificate):
        self.cert = certificate
        self.source = s = certificate.source
        self.branches, _ = branch_data((*s.residuals, *s.conditions), s.branch_choices)
        self.mapping = {**s.slot_map, **s.rate_map}
        occupied = {v.name for v in (*self.mapping.values(), s.time, *s.parameters)}
        self.composites = dict(certificate.normalization.rewrites)
        self.markers = {}
        for i, derivative in enumerate(self.composites):
            name = f"implicit_raw_rate_{i}"
            while name in occupied:
                name += "_"
            occupied.add(name)
            self.markers[derivative] = sp.Symbol(name, real=True)
        self.raw_mapping = {**self.mapping, **self.markers}
        self.rec = {
            self.mapping[k]: _jet(v, self.mapping)
            for k, v in certificate.reconstruction
        }
        self.rate_rec = {
            self.mapping[k]: _jet(v, self.mapping)
            for k, v in certificate.reconstruction_derivatives
        }
        self.conditions = tuple(
            _jet(v, self.mapping, True) for v in certificate.conditions
        )
        self.source_conditions = tuple(
            _jet(v, self.raw_mapping, True) for v in s.conditions
        )
        expressions = [
            _jet(v, self.raw_mapping, True) for v in (*s.residuals, *s.conditions)
        ]
        expressions += [_jet(v, self.mapping) for v in certificate.reduced_residuals]
        expressions += (
            list(self.conditions)
            + list(self.rec.values())
            + list(self.rate_rec.values())
            + list(s.interval)
        )
        for law in s.smooth_functions:
            expressions.extend(
                f(*([s.time] * law.arity)) for f in (law.function, *law.partials)
            )
        for derivative in self.composites:
            expressions.append(_jet(derivative.expr, self.mapping, True))
        self.printer = _LeanExpressionPrinter(
            expressions, (*self.mapping.values(), *s.parameters, s.time)
        )
        for expression in expressions:
            for node in sp.preorder_traversal(expression):
                if (
                    isinstance(node, sp.Function)
                    and node.func not in (sp.exp, sp.Piecewise)
                    and not isinstance(node, sp.core.function.AppliedUndef)
                ):
                    raise UnsupportedExpressionError(
                        f"implicit Lean export does not support {node.func}"
                    )
                if isinstance(node, sp.Pow) and node.exp.is_integer is not True:
                    raise UnsupportedExpressionError(
                        "implicit Lean export requires integer powers"
                    )
        self.prefix = "er_"
        while any(
            v.startswith(self.prefix)
            for v in (
                *self.printer.symbol_names.values(),
                *self.printer.function_names.values(),
            )
        ):
            self.prefix += "_"
        self.clock = self.prefix + "time"
        self.sample = self.prefix + "sample"
        self.xs = tuple(s.slot_map[v] for v in s.unknowns)
        self.us = tuple(s.slot_map[v] for v in s.inputs)
        self.velocities = tuple(
            s.rate_map[sp.Derivative(v, s.time)] for v in s.unknowns
        )
        self.input_velocities = tuple(
            s.rate_map[sp.Derivative(v, s.time)] for v in s.inputs
        )
        self.trajectories = {
            v: self.prefix + f"trajectory_{i}"
            for i, v in enumerate((*self.xs, *self.us))
        }
        self.retained = tuple(
            v for v in s.unknowns if v not in dict(certificate.reconstruction)
        )
        self.current = self.at(self.clock)
        self.nearby = self.at(self.sample)
        self.names = [f"hD{i}" for i in range(len(self.conditions))]
        self.field_names = [
            *self.names,
            *(["Real.exp_ne_zero"] if any(v.has(sp.exp) for v in expressions) else []),
        ]
        self.common = [f"({self.printer.symbol(v)} : ℝ)" for v in s.parameters]
        self.common += [
            f"({self.trajectories[v]} : ℝ → ℝ)" for v in (*self.xs, *self.us)
        ]
        self.functions = sorted(
            self.printer.function_arities, key=self.printer.function_names.get
        )
        self.common += [
            f"({self.printer.function_names[f]} : "
            + " → ".join(["ℝ"] * (self.printer.function_arities[f] + 1))
            + ")"
            for f in self.functions
        ]
        self.args = (
            [self.printer.symbol(v) for v in s.parameters]
            + [self.trajectories[v] for v in (*self.xs, *self.us)]
            + [self.printer.function_names[f] for f in self.functions]
        )
        self.membership = (
            f"{self.clock} ∈ Set.Ioo ({self.render(s.interval[0])}) "
            f"({self.render(s.interval[1])})"
        )
        self.smooth_binders = []
        self.smooth_names = []
        for i, law in enumerate(s.smooth_functions):
            name = f"hSmooth{i}"
            self.smooth_names.append(name)
            f = self.printer.function_names[law.function]
            ps = [self.printer.function_names[p] for p in law.partials]
            if law.arity == 1:
                proposition = f"∀ a : ℝ, HasDerivAt {f} ({ps[0]} a) a"
            else:
                proposition = (
                    f"∀ a b : ℝ, HasFDerivAt (fun p : ℝ × ℝ => {f} p.1 p.2) "
                    f"(({ps[0]} a b) • ContinuousLinearMap.fst ℝ ℝ ℝ + "
                    f"({ps[1]} a b) • ContinuousLinearMap.snd ℝ ℝ ℝ) (a,b)"
                )
            self.smooth_binders.append(f"({name} : {proposition})")
        self.common += self.smooth_binders
        self.args += self.smooth_names

    def at(self, point):
        values = {self.source.time: point}
        for state, slot in self.source.slot_map.items():
            name = self.trajectories[slot]
            values[slot] = f"({name} {point})"
            values[self.source.rate_map[sp.Derivative(state, self.source.time)]] = (
                f"(deriv {name} {point})"
            )
        for derivative, marker in self.markers.items():
            body = self.printer.print(
                _jet(derivative.expr, self.mapping, True),
                {
                    self.source.time: self.sample,
                    **{v: f"({f} {self.sample})" for v, f in self.trajectories.items()},
                },
            )
            values[marker] = f"(deriv (fun {self.sample} : ℝ => {body}) {point})"
        return values

    def render(self, expression, raw=False):
        return self.printer.print(
            _jet(expression, self.raw_mapping if raw else self.mapping, True),
            self.current,
        )

    def graph(self, point=None):
        point = point or self.clock
        at = self.at(point)
        return _conjunction(
            [
                f"({self.printer.print(k, at)} = {self.printer.print(v, at)})"
                for k, v in self.rec.items()
            ]
        )

    def diffs(self, states):
        return _conjunction(
            [
                f"DifferentiableAt ℝ {self.trajectories[self.mapping[v]]} {self.clock}"
                for v in states
            ]
        )

    def nz(self, expression):
        if expression.func is sp.exp:
            arg = self.printer.print(expression.args[0], self.current)
            return f"(Real.exp_ne_zero ({arg}))"
        for condition, name in zip(self.conditions, self.names, strict=True):
            if isinstance(condition, sp.Unequality):
                value = condition.lhs - condition.rhs
                if expression == value:
                    return name
                ratio = sp.cancel(value / expression)
                if (
                    ratio.as_numer_denom()[1].is_number
                    and sp.cancel(value - ratio * expression) == 0
                ):
                    return (
                        "(by intro hZero; apply " + name + "; linear_combination "
                        "(norm := ((try field_simp ["
                        + ", ".join(self.names)
                        + "]) <;> ring1)) ("
                        + self.printer.print(ratio, self.current)
                        + ") * hZero)"
                    )
        factor = sp.factor(expression)
        if factor.is_number:
            return (
                "(by norm_num : "
                + self.printer.print(expression, self.current)
                + " ≠ 0)"
            )
        if isinstance(factor, sp.Mul):
            terms = [self.nz(v) for v in factor.args]
            result = terms[0]
            for term in terms[1:]:
                result = f"(mul_ne_zero ({result}) ({term}))"
        elif isinstance(factor, sp.Pow) and factor.exp.is_Integer:
            result = f"(pow_ne_zero {abs(int(factor.exp))} ({self.nz(factor.base)}))"
            if factor.exp < 0:
                result = f"(inv_ne_zero ({result}))"
        else:
            raise UnsupportedExpressionError(
                f"no formal nonvanishing witness for {expression}"
            )
        if factor == expression:
            return result
        return (
            "(by convert "
            + result
            + " using 1 <;> (try field_simp ["
            + ", ".join(self.names)
            + "]) <;> ring)"
        )

    def guard(self, condition):
        if condition is sp.true:
            return "True.intro"
        if isinstance(condition, sp.Unequality):
            return self.nz(condition.lhs - condition.rhs)
        for known, name in zip(self.conditions, self.names, strict=True):
            if condition == known:
                return name
            if (
                isinstance(condition, Relational)
                and type(condition) is type(known)
                and sp.cancel(condition.lhs - condition.rhs - known.lhs + known.rhs)
                == 0
            ):
                return f"(by nlinarith only [{name}])"
        raise UnsupportedExpressionError(
            f"formal guard transport is unsupported: {condition}"
        )

    def calculate(self, expressions, prefix, guards):
        return rational_derivative_proofs(
            expressions,
            time=self.source.time,
            xs=(*self.xs, *self.us),
            velocities=(*self.velocities, *self.input_velocities),
            render=self.printer.print,
            current=self.current,
            nearby=self.nearby,
            clock=self.clock,
            sample=self.sample,
            guard_names=[*guards, "Real.exp_ne_zero"]
            if any(v.has(sp.exp) for v in expressions)
            else guards,
            rate_proofs=[f"hActualRate{i}" for i in range(len(self.xs) + len(self.us))],
            prefix=prefix,
            smooth_functions=self.source.smooth_functions,
            smooth_hypotheses=self.smooth_names,
        )

    def branch_facts(
        self, lines, guards, indent="  ", rewrites=(), point=None, prefix="hBranch"
    ):
        names: list[str] = []
        at = self.at(point or self.clock)
        for node, index in self.source.branch_choices:
            for j, (_, condition) in enumerate(node.args[: index + 1]):
                if condition is sp.true:
                    continue
                name = prefix + str(len(names))
                predicate = self.printer.print(_jet(condition, self.mapping, True), at)
                if j < index:
                    predicate = f"¬ {predicate}"
                lines += [
                    f"{indent}have {name} : {predicate} := by",
                    indent
                    + "  "
                    + (
                        "(try simp only [" + ", ".join(rewrites) + "]) <;> "
                        if rewrites
                        else ""
                    )
                    + "first | assumption | (linarith only ["
                    + ", ".join(guards)
                    + "])",
                ]
                names.append(name)
        return names

    def input_regularity_binders(self):
        if not self.source.inputs:
            return []
        return [
            f"(hInputRegularity : ∀ {self.clock} : ℝ, {self.membership} → "
            f"({self.diffs(self.source.inputs)}))"
        ]

    def input_diffs_at(self, lines, indent="    "):
        names = [f"hInputDiff{i}" for i in range(len(self.us))]
        if names:
            lines.append(f"{indent}have hInputs := hInputRegularity {self.clock} hTime")
            _unpack(lines, "hInputs", names, indent)
        return names


def generate_implicit_lean(certificate):
    from equireduce.lean import generate_lean

    c = Context(certificate)
    s = c.source
    for index in certificate.algebraic_row_indices:
        if (
            s.residuals[index].has(sp.Derivative)
            and certificate.normalization.residuals[index] != 0
        ):
            raise UnsupportedExpressionError(
                "a normalized static pivot with a raw derivative needs "
                "an additional normalization lemma"
            )
    inner = certificate.algebraic
    static = System.algebraic(
        inner.source.residuals,
        inner.source.unknowns,
        parameters=inner.source.parameters,
        residual_names=inner.source.residual_names,
    )
    rate_symbols = set(s.rate_map.values())
    core = replace(
        inner.reduction,
        conditions=tuple(
            v for v in inner.reduction.conditions if not v.free_symbols & rate_symbols
        ),
    )
    helper_cert = Certificate(static, core)
    if verify_certificate(static, helper_cert).status.value != "verified":
        raise UnsupportedExpressionError(
            "cannot isolate the algebraic reconstruction proof"
        )
    helper = (
        generate_lean(static, helper_cert)
        .replace("theorem reduction_equivalence", "theorem algebraic_reconstruction")
        .replace("#print axioms reduction_equivalence", "")
    )
    lines = [
        "import Mathlib.Analysis.Calculus.Deriv.Pow\n"
        "import Mathlib.Analysis.Calculus.Deriv.Inv\n"
        "import Mathlib.Analysis.Calculus.Deriv.Add\n"
        "import Mathlib.Tactic.Convert\n" + helper
    ]
    if s.smooth_functions or any(v.has(sp.exp) for v in s.residuals):
        lines[0] = (
            "import Mathlib.Analysis.Calculus.Deriv.Prod\n"
            "import Mathlib.Analysis.SpecialFunctions.ExpDeriv\n" + lines[0]
        )
    point_binders = [
        *c.common,
        f"({c.clock} : ℝ)",
        f"(hTime : {c.membership})",
        f"(hGraph : ∀ {c.clock} : ℝ, {c.membership} → ({c.graph()}))",
    ]
    if c.branches:
        domain = _conjunction([c.printer.print(v, c.current) for v in c.conditions])
        point_binders.append(
            f"(hBranchRegion : ∀ {c.clock} : ℝ, {c.membership} → ({domain}))"
        )
    point_binders += [
        f"(hDiff{i} : DifferentiableAt ℝ {c.trajectories[c.mapping[v]]} {c.clock})"
        for i, v in enumerate((*c.retained, *s.inputs))
    ]
    point_binders += [
        f"({name} : {c.printer.print(cond, c.current)})"
        for name, cond in zip(c.names, c.conditions, strict=True)
    ]
    source_domains = _conjunction([c.render(v, True) for v in s.conditions])
    targets = {
        index: certificate.reduced_residuals[i]
        for i, index in enumerate(certificate.residual_source_indices)
    }
    images = _conjunction(
        [
            f"({c.render(row, True)} = {c.render(targets.get(i, sp.S.Zero))})"
            for i, row in enumerate(s.residuals)
        ]
    )
    lines += [
        "theorem implicit_point_transport " + " ".join(point_binders) + " :",
        f"    ({c.diffs(s.unknowns)}) ∧ ({source_domains}) ∧ ({images}) := by",
        "  classical",
        f"  have hValues := hGraph {c.clock} hTime",
    ]
    value_names = [f"hValue{i}" for i in range(len(c.rec))]
    _unpack(lines, "hValues", value_names, "  ")
    for i, state in enumerate((*c.retained, *s.inputs)):
        index = (*s.unknowns, *s.inputs).index(state)
        lines.append(f"  have hActualRate{index} := hDiff{i}.hasDerivAt")
    calculations, phi_proofs = c.calculate(tuple(c.rec.values()), "Rec", c.names)
    lines.extend(calculations)
    rate_names = []
    for i, ((state, _phi), proof) in enumerate(
        zip(c.rec.items(), phi_proofs, strict=True)
    ):
        state_index = c.xs.index(state)
        rate = c.rate_rec[c.velocities[state_index]]
        lines += [
            f"  have hYHas{i} : HasDerivAt {c.trajectories[state]} "
            f"({c.printer.print(rate, c.current)}) {c.clock} := by",
            "    refine HasDerivAt.congr_of_eventuallyEq "
            f"(({proof}).congr_deriv ?_) ?_",
            "    · (try field_simp [" + ", ".join(c.field_names) + "]) <;> ring",
            "    · filter_upwards [Ioo_mem_nhds hTime.1 hTime.2] with "
            + c.sample
            + " hNear",
            f"      have hNearValues := hGraph {c.sample} hNear",
        ]
        near_names = [f"hNearValue{j}" for j in range(len(c.rec))]
        _unpack(lines, "hNearValues", near_names, "      ")
        lines += [
            "      exact " + near_names[i],
            f"  have hActualRate{state_index} := hYHas{i}.differentiableAt.hasDerivAt",
            f"  have hYRate{i} := hYHas{i}.deriv",
        ]
        rate_names.append(f"hYRate{i}")
    facts = [*value_names, *rate_names]
    # Domains of raw rational charge expressions are established on the graph.
    charge_exprs = [
        _jet(raw_replace(d.expr, c.branches), c.mapping, True) for d in c.composites
    ]
    branch_names = c.branch_facts(lines, c.names, rewrites=value_names)
    denom_names = []
    for i, guard in enumerate(domain_conditions(charge_exprs)):
        projected = substitute_condition(guard, c.rec)
        proof = c.guard(projected)
        name = f"hNormalizationDomain{i}"
        lines += [
            f"  have {name} : {c.printer.print(guard, c.current)} := by",
            "    (try simp only ["
            + ", ".join(value_names)
            + "]) <;> convert "
            + proof
            + " using 1 <;> (try field_simp ["
            + ", ".join(c.field_names)
            + "]) <;> ring",
        ]
        denom_names.append(name)
    calculations, charge_proofs = c.calculate(
        charge_exprs, "Norm", [*c.names, *denom_names]
    )
    lines.extend(calculations)
    for i, (derivative, proof) in enumerate(
        zip(c.composites, charge_proofs, strict=True)
    ):
        if c.branches and _jet(derivative.expr, c.mapping, True) != charge_exprs[i]:
            raw_body = _jet(derivative.expr, c.mapping, True)
            raw_fn = f"(fun {c.sample} : ℝ => {c.printer.print(raw_body, c.nearby)})"
            rate = c.printer.print(_jet(c.composites[derivative], c.mapping), c.current)
            lines += [
                f"  have hRawChain{i} : HasDerivAt {raw_fn} ({rate}) {c.clock} := by",
                "    refine HasDerivAt.congr_of_eventuallyEq "
                f"(({proof}).congr_deriv ?_) ?_",
                "    · "
                + (
                    "(try simp only [neg_one_mul, Real.exp_add, "
                    "Real.exp_sub, Real.exp_neg]) <;> "
                    if s.smooth_functions or raw_body.has(sp.exp)
                    else ""
                )
                + "(try field_simp ["
                + ", ".join(c.field_names)
                + "]) <;> ring",
                "    · filter_upwards [Ioo_mem_nhds hTime.1 hTime.2] with "
                f"{c.sample} hNear",
                f"      have hNearDomain := hBranchRegion {c.sample} hNear",
                f"      have hNearGraph := hGraph {c.sample} hNear",
            ]
            ng = [f"hNearD{k}" for k in range(len(c.names))]
            nv = [f"hNearV{k}" for k in range(len(value_names))]
            _unpack(lines, "hNearDomain", ng, "      ")
            _unpack(lines, "hNearGraph", nv, "      ")
            bn = c.branch_facts(lines, ng, "      ", nv, c.sample, f"hNearBranch{i}_")
            lines.append(
                "      simp only [" + ", ".join([*bn, "ite_true", "ite_false"]) + "]"
            )
            proof = f"hRawChain{i}"
        lines.append(f"  have hNormalization{i} := ({proof}).deriv")
        facts.append(f"hNormalization{i}")
    simplify = (
        "(try simp only ["
        + ", ".join(
            [*facts, *branch_names, "ite_true", "ite_false"] if branch_names else facts
        )
        + "]) <;> "
        + (
            "(try simp only [neg_one_mul,Real.exp_add,Real.exp_sub,Real.exp_neg]) <;> "
            if s.smooth_functions or any(v.has(sp.exp) for v in s.residuals)
            else ""
        )
        + "(try field_simp ["
        + ", ".join(
            [
                *c.names,
                *denom_names,
                *(
                    ["Real.exp_ne_zero"]
                    if any(v.has(sp.exp) for v in s.residuals)
                    else []
                ),
            ]
        )
        + "]) <;> (try ring_nf) <;> ring"
    )
    for i, condition in enumerate(s.conditions):
        projected = substitute_condition(condition, dict(c.composites))
        projected = substitute_condition(
            substitute_condition(
                projected, dict(certificate.reconstruction_derivatives)
            ),
            dict(certificate.reconstruction),
        )
        proof = c.guard(_jet(projected, c.mapping, True))
        lines += [
            f"  have hSourceDomain{i} : {c.render(condition, True)} := by",
            "    (try simp only ["
            + ", ".join(facts)
            + "]) <;> convert "
            + proof
            + " using 1 <;> (try field_simp ["
            + ", ".join(c.field_names)
            + "]) <;> (try ring_nf) <;> ring",
        ]
    for i, row in enumerate(s.residuals):
        lines += [
            f"  have hImage{i} : {c.render(row, True)} = "
            f"{c.render(targets.get(i, sp.S.Zero))} := by",
            "    " + simplify,
        ]
    diff_proofs = []
    for state in s.unknowns:
        if state in c.retained:
            diff_proofs.append(f"hDiff{c.retained.index(state)}")
        else:
            diff_proofs.append(
                f"hYHas{list(c.rec).index(c.mapping[state])}.differentiableAt"
            )
    lines.append(
        "  exact ⟨"
        + _tuple(diff_proofs)
        + ", "
        + _tuple([f"hSourceDomain{i}" for i in range(len(s.conditions))])
        + ", "
        + _tuple([f"hImage{i}" for i in range(len(s.residuals))])
        + "⟩"
    )
    domain = _conjunction([c.printer.print(v, c.current) for v in c.conditions])
    original = _conjunction([f"({c.render(v, True)} = 0)" for v in s.residuals])
    reduced = _conjunction(
        [f"({c.render(v)} = 0)" for v in certificate.reduced_residuals]
    )
    outer = [
        *c.common,
        f"(hInterval : ({c.render(s.interval[0])}) < ({c.render(s.interval[1])}))",
        *c.input_regularity_binders(),
        f"(hDomain : ∀ {c.clock} : ℝ, {c.membership} → ({domain}))",
    ]
    lines += [
        "theorem reduction_equivalence " + " ".join(outer) + " :",
        f"    (∀ {c.clock} : ℝ, {c.membership} → "
        f"(({c.diffs(s.unknowns)}) ∧ ({source_domains}) ∧ ({original}))) ↔",
        f"    ((∀ {c.clock} : ℝ, {c.membership} → "
        f"(({c.diffs(c.retained)}) ∧ ({reduced}))) ∧ "
        f"(∀ {c.clock} : ℝ, {c.membership} → ({c.graph()}))) := by",
        "  classical",
        "  constructor",
        "  · intro hSource",
        f"    have hGraph : ∀ {c.clock} : ℝ, {c.membership} → ({c.graph()}) := by",
        f"      intro {c.clock} hTime",
        f"      rcases hSource {c.clock} hTime with ⟨hDiff, hSDomain, hRows⟩",
        f"      have hGuards := hDomain {c.clock} hTime",
    ]
    _unpack(lines, "hGuards", c.names, "      ")
    source_names = [f"hS{i}" for i in range(len(s.conditions))]
    row_names = [f"hRaw{i}" for i in range(len(s.residuals))]
    _unpack(lines, "hSDomain", source_names, "      ")
    _unpack(lines, "hRows", row_names, "      ")
    forward_branches = c.branch_facts(
        lines, source_names, "      ", prefix="hForwardBranch"
    )
    helper_conditions = []
    for condition in core.conditions:
        simplified = simplify_condition(condition)
        if simplified is not sp.true:
            condition = simplified
        if condition is not sp.true and condition not in helper_conditions:
            helper_conditions.append(condition)
    helper_guards = []
    for i, condition in enumerate(helper_conditions):
        name = f"hHelperDomain{i}"
        helper_guards.append(name)
        lines += [
            f"      have {name} : {c.printer.print(condition, c.current)} := by",
            "        exact " + c.guard(condition),
        ]
    static_names = []
    for j, index in enumerate(certificate.algebraic_row_indices):
        name = f"hStatic{j}"
        static_names.append(name)
        if static.residuals[j] == 0:
            lines.append(f"      have {name} : (0 : ℝ) = 0 := rfl")
            continue
        lines += [
            f"      have {name} : "
            f"{c.printer.print(static.residuals[j], c.current)} = 0 := by",
            f"        convert {row_names[index]} using 1 <;> "
            + (
                "(try simp only ["
                + ", ".join([*forward_branches, "ite_true", "ite_false"])
                + "]) <;> "
                if forward_branches
                else ""
            )
            + "(try field_simp ["
            + ", ".join(
                [
                    *source_names,
                    *(
                        ["Real.exp_ne_zero"]
                        if any(v.has(sp.exp) for v in s.residuals)
                        else []
                    ),
                ]
            )
            + "]) <;> (try ring_nf) <;> ring",
        ]
        if any(v.has(sp.exp) for v in s.residuals):
            lines[-1] = lines[-1].replace(
                "(try field_simp [",
                "(try simp only [neg_one_mul, Real.exp_add, "
                "Real.exp_sub, Real.exp_neg]) <;> (try field_simp [",
                1,
            )
    expressions = proof_expressions(core)
    hp = _LeanExpressionPrinter(expressions, core.source_unknowns)
    symbols = set(core.source_unknowns)
    for expression in expressions:
        symbols.update(expression.free_symbols)
    order = list(core.source_unknowns) + sorted(
        symbols - set(core.source_unknowns), key=lambda v: (str(v), sp.srepr(v))
    )
    args = (
        [c.printer.print(v, c.current) for v in order]
        + [
            c.printer.function_names[f]
            for f in sorted(hp.function_arities, key=hp.function_names.get)
        ]
        + helper_guards
    )
    app = "(algebraic_reconstruction " + " ".join(f"({v})" for v in args) + ")"
    lines += [
        f"      exact ({app}.mp " + _tuple(static_names) + ").2",
        "    refine ⟨?_, hGraph⟩",
        f"    intro {c.clock} hTime",
        f"    rcases hSource {c.clock} hTime with ⟨hDiff, hSDomain, hRows⟩",
        f"    have hGuards := hDomain {c.clock} hTime",
    ]
    _unpack(lines, "hGuards", c.names)
    all_diff_names = [f"hAllDiff{i}" for i in range(len(s.unknowns))]
    _unpack(lines, "hDiff", all_diff_names)
    _unpack(lines, "hRows", row_names)
    retained_diff = [all_diff_names[s.unknowns.index(v)] for v in c.retained]
    input_diff = c.input_diffs_at(lines)
    point_args = [
        *c.args,
        c.clock,
        "hTime",
        "hGraph",
        *(["hDomain"] if c.branches else []),
        *retained_diff,
        *input_diff,
        *c.names,
    ]
    point_app = (
        "(implicit_point_transport " + " ".join(f"({v})" for v in point_args) + ")"
    )
    lines.append(f"    rcases {point_app} with ⟨hAllDiff, hAllDomain, hImages⟩")
    image_names = [f"hImage{i}" for i in range(len(s.residuals))]
    _unpack(lines, "hImages", image_names)
    kept = []
    for j, index in enumerate(certificate.residual_source_indices):
        name = f"hReduced{j}"
        kept.append(name)
        lines.append(
            f"    have {name} := {image_names[index]}.symm.trans {row_names[index]}"
        )
    lines += [
        "    exact ⟨" + _tuple(retained_diff) + ", " + _tuple(kept) + "⟩",
        "  · rintro ⟨hReduced, hGraph⟩",
        f"    intro {c.clock} hTime",
        f"    rcases hReduced {c.clock} hTime with ⟨hDiff, hRows⟩",
        f"    have hGuards := hDomain {c.clock} hTime",
    ]
    _unpack(lines, "hGuards", c.names)
    retained_names = [f"hRetainedDiff{i}" for i in range(len(c.retained))]
    _unpack(lines, "hDiff", retained_names)
    input_diff = c.input_diffs_at(lines)
    point_args = [
        *c.args,
        c.clock,
        "hTime",
        "hGraph",
        *(["hDomain"] if c.branches else []),
        *retained_names,
        *input_diff,
        *c.names,
    ]
    lines.append(
        "    rcases (implicit_point_transport "
        + " ".join(f"({v})" for v in point_args)
        + ") with ⟨hAllDiff, hAllDomain, hImages⟩"
    )
    _unpack(lines, "hImages", image_names)
    reduced_names = [
        f"hReducedRow{i}" for i in range(len(certificate.reduced_residuals))
    ]
    _unpack(lines, "hRows", reduced_names)
    for i in range(len(s.residuals)):
        value = (
            reduced_names[certificate.residual_source_indices.index(i)]
            if i in certificate.residual_source_indices
            else "rfl"
        )
        lines.append(f"    have hSourceRow{i} := {image_names[i]}.trans ({value})")
    lines += [
        "    exact ⟨hAllDiff, hAllDomain, "
        + _tuple([f"hSourceRow{i}" for i in range(len(s.residuals))])
        + "⟩",
        "#print axioms reduction_equivalence",
    ]
    return "\n".join(lines) + "\n"
