"""Certificate-to-Lean algebraic exporter, derived from the Dnipro prototype."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence

import sympy as sp

from equireduce._core import (
    ReductionResult,
    ReductionStep,
    build_reduction_certificate,
    verify_reduction_certificate,
)
from equireduce.conditions import simplify_condition


def _nonzero_factors(expression):
    """Exact factor support for nonvanishing, without Boolean numeric probes."""
    expression = sp.factor(expression)
    if expression.is_number and expression.is_zero is False:
        return frozenset()
    if isinstance(expression, sp.Mul):
        return frozenset().union(*(_nonzero_factors(v) for v in expression.args))
    if (
        isinstance(expression, sp.Pow)
        and expression.exp.is_Integer
        and expression.exp != 0
    ):
        return _nonzero_factors(expression.base)
    return frozenset((expression,))


class LeanExportError(ValueError):
    """Raised when an expression cannot be translated to Lean 4."""


_LEAN_KEYWORDS = {
    "abbrev",
    "at",
    "by",
    "do",
    "else",
    "end",
    "example",
    "false",
    "for",
    "fun",
    "have",
    "if",
    "import",
    "in",
    "let",
    "match",
    "namespace",
    "open",
    "private",
    "protected",
    "public",
    "section",
    "set_option",
    "structure",
    "syntax",
    "theorem",
    "then",
    "true",
    "universe",
    "where",
}


class _LeanExpressionPrinter:
    def __init__(self, expressions: Sequence[sp.Expr], unknowns: Sequence[sp.Expr]):
        symbols = set(unknowns)
        functions: dict[sp.FunctionClass, int] = {}
        for expression in expressions:
            symbols.update(expression.free_symbols)
            for applied in expression.atoms(sp.core.function.AppliedUndef):
                function = applied.func
                arity = len(applied.args)
                if function in functions and functions[function] != arity:
                    raise LeanExportError(
                        f"undefined function {function} occurs with multiple arities"
                    )
                functions[function] = arity

        self.symbol_names = self._allocate_names(
            (symbol for symbol in symbols if isinstance(symbol, sp.Symbol)),
            prefix="sym",
        )
        self.function_names = self._allocate_names(
            functions, prefix="uf", prepend_prefix=True
        )
        self.function_arities = functions

    @staticmethod
    def _identifier(name: str, prefix: str) -> str:
        result = re.sub(r"[^A-Za-z0-9_']", "_", name)
        if not result or not result[0].isalpha():
            result = f"{prefix}_{result}"
        if result in _LEAN_KEYWORDS:
            result = f"{prefix}_{result}"
        return result

    @classmethod
    def _allocate_names(cls, objects, *, prefix: str, prepend_prefix: bool = False):
        result = {}
        used: set[str] = set()
        for obj in sorted(
            objects,
            key=lambda item: (
                str(item),
                sp.srepr(item),
                repr(sorted(getattr(item, "_kwargs", {}).items())),
            ),
        ):
            raw_name = f"{prefix}_{obj}" if prepend_prefix else str(obj)
            candidate = cls._identifier(raw_name, prefix)
            base = candidate
            suffix = 2
            while candidate in used:
                candidate = f"{base}_{suffix}"
                suffix += 1
            used.add(candidate)
            result[obj] = candidate
        return result

    def symbol(self, value: sp.Symbol) -> str:
        try:
            return self.symbol_names[value]
        except KeyError as exc:
            raise LeanExportError(
                f"unbound symbol in Lean expression: {value}"
            ) from exc

    def print(
        self, expression, substitutions: Mapping[sp.Symbol, str] | None = None
    ) -> str:
        expression = sp.sympify(expression)
        if expression is sp.true:
            return "True"
        if expression is sp.false:
            return "False"
        if isinstance(expression, sp.Symbol):
            if substitutions is not None and expression in substitutions:
                return substitutions[expression]
            return self.symbol(expression)
        if isinstance(expression, sp.Integer):
            return f"({int(expression)} : ℝ)"
        if isinstance(expression, sp.Rational):
            return f"(({int(expression.p)} : ℝ) / ({int(expression.q)} : ℝ))"
        if isinstance(expression, sp.Float):
            rational = sp.Rational(str(expression))
            return self.print(rational)
        if expression is sp.pi:
            return "Real.pi"
        if expression is sp.E:
            return "Real.exp (1 : ℝ)"
        if isinstance(expression, sp.Add):
            return (
                "("
                + " + ".join(self.print(arg, substitutions) for arg in expression.args)
                + ")"
            )
        if isinstance(expression, sp.Mul):
            return (
                "("
                + " * ".join(self.print(arg, substitutions) for arg in expression.args)
                + ")"
            )
        if isinstance(expression, sp.Pow):
            return self._power(expression.base, expression.exp, substitutions)
        if isinstance(expression, sp.Piecewise):
            value = "(0 : ℝ)"
            for branch, condition in reversed(expression.args):
                if condition is sp.true:
                    value = self.print(branch, substitutions)
                else:
                    value = (
                        f"(if {self.print(condition, substitutions)} then "
                        f"{self.print(branch, substitutions)} "
                        f"else {value})"
                    )
            return value
        if isinstance(expression, sp.Abs):
            return f"(abs {self.print(expression.args[0], substitutions)})"
        if isinstance(expression, sp.Max | sp.Min):
            operation = "max" if isinstance(expression, sp.Max) else "min"
            values = [self.print(arg, substitutions) for arg in expression.args]
            return f"({operation} {values[0]} {values[1]})"
        if isinstance(expression, sp.core.relational.Relational):
            symbols = {
                sp.Equality: "=",
                sp.Unequality: "≠",
                sp.StrictLessThan: "<",
                sp.LessThan: "≤",
                sp.StrictGreaterThan: ">",
                sp.GreaterThan: "≥",
            }
            relation_operation = symbols.get(type(expression))
            if relation_operation is None:
                raise LeanExportError(
                    f"unsupported relation in Lean expression: {expression.func}"
                )
            return (
                f"({self.print(expression.lhs, substitutions)} {relation_operation} "
                f"{self.print(expression.rhs, substitutions)})"
            )
        if isinstance(expression, sp.And | sp.Or):
            operation = "∧" if isinstance(expression, sp.And) else "∨"
            return (
                "("
                + f" {operation} ".join(
                    self.print(arg, substitutions) for arg in expression.args
                )
                + ")"
            )
        if isinstance(expression, sp.Not):
            return f"(¬ {self.print(expression.args[0], substitutions)})"
        if isinstance(expression, sp.core.function.AppliedUndef):
            function_name = self.function_names[expression.func]
            args = " ".join(self.print(arg, substitutions) for arg in expression.args)
            return f"({function_name} {args})"

        known_functions = {
            sp.exp: "Real.exp",
            sp.log: "Real.log",
            sp.sin: "Real.sin",
            sp.cos: "Real.cos",
            sp.tan: "Real.tan",
            sp.sinh: "Real.sinh",
            sp.cosh: "Real.cosh",
            sp.tanh: "Real.tanh",
            sp.asin: "Real.arcsin",
            sp.acos: "Real.arccos",
            sp.atan: "Real.arctan",
        }
        if expression.func in known_functions:
            name = known_functions[expression.func]
            if expression.func is sp.log and len(expression.args) == 2:
                numerator = f"Real.log {self.print(expression.args[0], substitutions)}"
                denominator = (
                    f"Real.log {self.print(expression.args[1], substitutions)}"
                )
                return f"({numerator} / {denominator})"
            return f"({name} {self.print(expression.args[0], substitutions)})"

        raise LeanExportError(
            f"unsupported SymPy expression in Lean export: {expression.func}"
        )

    def _power(
        self,
        base: sp.Expr,
        exponent: sp.Expr,
        substitutions: Mapping[sp.Symbol, str] | None = None,
    ) -> str:
        base_text = self.print(base, substitutions)
        exponent = sp.sympify(exponent)
        if exponent.is_Integer:
            integer = int(exponent)
            if integer >= 0:
                return f"({base_text} ^ {integer})"
            return f"((1 : ℝ) / ({base_text} ^ {-integer}))"
        if exponent == sp.Rational(1, 2):
            return f"(Real.sqrt {base_text})"
        if exponent == sp.Rational(-1, 2):
            return f"((1 : ℝ) / Real.sqrt {base_text})"
        exponent_text = self.print(exponent, substitutions)
        return f"(Real.rpow {base_text} {exponent_text})"


def _conjunction(expressions: Sequence[str]) -> str:
    if not expressions:
        return "True"
    return " ∧ ".join(f"({expression})" for expression in expressions)


def _tactic_conditions(conditions: Sequence[str]) -> str:
    return "[" + ", ".join(conditions) + "]"


def proof_expressions(result: ReductionResult):
    expressions = [
        *result.source_residuals,
        *result.reduced_residuals,
        *(value for _, value in result.reconstruction),
        *result.conditions,
    ]
    for step in result.steps:
        if isinstance(step, ReductionStep):
            expressions.extend([step.coefficient, step.remainder, step.pivot_residual])
        else:
            expressions.extend(
                [
                    *step.coefficient_matrix,
                    *step.offset,
                    *step.pivot_residuals,
                    step.determinant,
                    *(value for _, value in step.reconstruction),
                ]
            )
    return expressions


def generate_lean_reduction_source(result: ReductionResult) -> str:
    """Generate a Mathlib theorem proving source/reduced system equivalence."""
    certificate = build_reduction_certificate(result)
    verification = verify_reduction_certificate(result, certificate)
    if verification.status.value != "verified":
        raise LeanExportError("SymPy reduction certificate did not verify")

    expressions = proof_expressions(result)
    printer = _LeanExpressionPrinter(expressions, result.source_unknowns)
    print_expr = printer.print

    formal_conditions = list(result.conditions)
    conditions: list[sp.Expr] = []
    for condition in formal_conditions:
        simplified = simplify_condition(condition)
        if simplified is not sp.true:
            condition = simplified
        if condition is not sp.true and condition not in conditions:
            conditions.append(condition)
    condition_names = [f"hCond{i}" for i in range(len(conditions))]

    all_symbols = set(result.source_unknowns)
    for expression in expressions:
        all_symbols.update(expression.free_symbols)
    symbol_order = list(result.source_unknowns) + sorted(
        all_symbols - set(result.source_unknowns),
        key=lambda item: (str(item), sp.srepr(item)),
    )
    binders = [f"({printer.symbol(symbol)} : ℝ)" for symbol in symbol_order]
    for function, arity in sorted(
        printer.function_arities.items(),
        key=lambda item: printer.function_names[item[0]],
    ):
        function_name = printer.function_names[function]
        function_type = " → ".join(["ℝ"] * (arity + 1))
        binders.append(f"({function_name} : {function_type})")
    binders.extend(
        f"({name} : {print_expr(condition)})"
        for name, condition in zip(condition_names, conditions, strict=True)
    )

    source_equations = [
        f"({print_expr(value)} = 0)" for value in result.source_residuals
    ]
    reduced_equations = [
        f"({print_expr(value)} = 0)" for value in result.reduced_residuals
    ]
    reconstruction_equations = [
        f"({printer.symbol(variable)} = {print_expr(expression)})"
        for variable, expression in result.reconstruction
    ]
    source_prop = _conjunction(source_equations)
    reduced_prop = _conjunction(reduced_equations)
    reconstruction_prop = _conjunction(reconstruction_equations)

    denominator_facts = []
    denominator_names: list[str] = []
    denominators = tuple(
        dict.fromkeys(
            sp.together(expression).as_numer_denom()[1]
            for expression in expressions
            if isinstance(expression, sp.Expr)
        )
    )
    for denominator in denominators:
        if denominator.is_number:
            continue
        for condition, hypothesis in zip(conditions, condition_names, strict=True):
            if isinstance(condition, sp.Unequality) and _nonzero_factors(
                denominator
            ) == _nonzero_factors(condition.lhs - condition.rhs):
                fact = f"hDen{len(denominator_names)}"
                denominator_facts.extend(
                    [
                        f"  have {fact} : {print_expr(denominator)} ≠ 0 := by",
                        "    intro hZero",
                        f"    apply {hypothesis}",
                        "    nlinarith only [hZero]",
                    ]
                )
                denominator_names.append(fact)
                break
    condition_names.extend(denominator_names)
    has_exp = any(v.has(sp.exp) for v in expressions)
    exp_rules = "neg_one_mul, Real.exp_add, Real.exp_sub, Real.exp_neg"
    if has_exp:
        condition_names.append("Real.exp_ne_zero")

    def proof_using(hypothesis, rewrites=(), indent="      "):
        proof_lines = [indent + "have hBase := " + hypothesis]
        if rewrites:
            proof_lines.append(
                indent + "try simp only [" + ", ".join(rewrites) + "] at hBase"
            )
        if has_exp:
            proof_lines.append(indent + f"try simp only [{exp_rules}] at hBase ⊢")
        normalizer = (
            "linear_combination (norm := ((try field_simp "
            + _tactic_conditions(condition_names)
            + ") <;> ring1)) hBase"
        )
        proof_lines.extend(
            [
                indent + "first",
                indent + "| " + normalizer,
                indent + "| (ring_nf at hBase ⊢",
                indent + "   all_goals " + normalizer + ")",
            ]
        )
        return proof_lines

    lines = [
        "import Mathlib.Basic.Real.Basic",
        "import Mathlib.Tactic.FieldSimp",
        "import Mathlib.Tactic.LinearCombination",
        "import Mathlib.Tactic.Linarith",
        "import Mathlib.Tactic.NormNum",
        "import Mathlib.Tactic.Ring",
        "set_option linter.unusedVariables false",
        "set_option linter.unnecessarySeqFocus false",
        "set_option linter.unusedTactic false",
        "set_option linter.unreachableTactic false",
        "set_option linter.unusedSimpArgs false",
        "set_option maxHeartbeats 2000000",
        "",
        "/- Exact algebraic equivalence from an EquiReduce certificate. -/",
        "theorem reduction_equivalence " + " ".join(binders) + " :",
        f"    ({source_prop}) ↔ (({reduced_prop}) ∧ ({reconstruction_prop})) := by",
        "  classical",
        *denominator_facts,
        "  constructor",
        "  · intro hSource",
    ]
    if len(source_equations) > 1:
        lines.append(
            "    rcases hSource with "
            + "⟨"
            + ", ".join(f"hSource{i}" for i in range(len(source_equations)))
            + "⟩"
        )
    elif source_equations:
        lines.append("    have hSource0 := hSource")

    step_proofs: dict[sp.Expr, str] = {}
    step_indices: dict[sp.Expr, int] = {}
    for step_number, step in enumerate(result.steps):
        current_prior_names: dict[sp.Expr, str] = {}
        for variable, prior_expression in step.prior_substitutions:
            proof_name = f"hPrior{step_number}_{printer.symbol(variable)}"
            later_names = [
                name
                for later_variable, name in step_proofs.items()
                if step_indices[later_variable] < step_number
                and step_indices[later_variable] > step_indices.get(variable, -1)
            ]
            if variable not in step_proofs:
                raise LeanExportError("step prior map references an unknown pivot")
            lines.append(
                f"    have {proof_name} : {printer.symbol(variable)} = "
                f"{print_expr(prior_expression)} := by"
            )
            lines.extend(proof_using(step_proofs[variable], later_names))
            current_prior_names[variable] = proof_name

        sources: tuple[tuple[int, sp.Expr | None], ...]
        if isinstance(step, ReductionStep):
            sources = ((step.equation_index, step.pivot_residual),)
        else:
            sources = tuple(
                zip(step.equation_indices, step.pivot_residuals, strict=True)
            )
        pivot_hypotheses = []
        for local_index, (source_index, pivot_residual) in enumerate(sources):
            trace_name = f"hTrace{step_number}_{local_index}"
            prior_map = dict(step.prior_substitutions)
            source_image = result.source_residuals[source_index].subs(
                prior_map, simultaneous=True
            )
            lines.extend(
                [
                    f"    have {trace_name} : {print_expr(source_image)} = "
                    f"{print_expr(pivot_residual)} := by",
                    "      "
                    + (f"(try simp only [{exp_rules}]) <;> " if has_exp else "")
                    + f"field_simp {_tactic_conditions(condition_names)} <;> ring",
                ]
            )
            current_name = f"hCurrent{step_number}_{local_index}"
            lines.append(
                f"    have {current_name} : {print_expr(source_image)} = 0 := by"
            )
            lines.extend(
                proof_using(
                    f"hSource{source_index}", tuple(current_prior_names.values())
                )
            )
            pivot_name = f"hPivot{step_number}_{local_index}"
            lines.extend(
                [
                    f"    have {pivot_name} : {print_expr(pivot_residual)} = 0 := by",
                    f"      rw [{trace_name}] at {current_name}",
                    f"      exact {current_name}",
                ]
            )
            pivot_hypotheses.append(pivot_name)

        if has_exp:
            lines.append(
                f"    try simp only [{exp_rules}] at " + " ".join(pivot_hypotheses)
            )

        if isinstance(step, ReductionStep):
            proof_name = f"hStep{step_number}_{printer.symbol(step.variable)}"
            lines.extend(
                [
                    f"    have {proof_name} : {printer.symbol(step.variable)} = "
                    f"{print_expr(step.reconstruction_expression)} := by",
                    (f"      try simp only [{exp_rules}]\n" if has_exp else "")
                    + "      try field_simp "
                    + _tactic_conditions(condition_names)
                    + " at "
                    + pivot_hypotheses[0]
                    + " ⊢\n      first | linear_combination "
                    + pivot_hypotheses[0]
                    + " | linarith only ["
                    + pivot_hypotheses[0]
                    + "]",
                ]
            )
            step_proofs[step.variable] = proof_name
            step_indices[step.variable] = step_number
        else:
            coefficient_matrix = sp.Matrix(step.coefficient_matrix)
            offset = sp.Matrix(step.offset)
            adjugate = coefficient_matrix.adjugate()
            for variable_index, (variable, value) in enumerate(step.reconstruction):
                linear_name = f"hBlock{step_number}_{printer.symbol(variable)}"
                numerator = (adjugate * offset)[variable_index]
                lines.extend(
                    [
                        f"    have {linear_name} : ({print_expr(step.determinant)}) * "
                        f"{printer.symbol(variable)} + "
                        f"{print_expr(numerator)} = 0 := by",
                        "      linear_combination "
                        + " + ".join(
                            f"({print_expr(adjugate[variable_index, column])})"
                            f" * {hypothesis}"
                            for column, hypothesis in enumerate(pivot_hypotheses)
                        ),
                    ]
                )
                proof_name = f"hStep{step_number}_{printer.symbol(variable)}"
                lines.extend(
                    [
                        f"    have {proof_name} : {printer.symbol(variable)} = "
                        f"{print_expr(value)} := by",
                        "      try field_simp "
                        + _tactic_conditions(condition_names)
                        + f" at {linear_name} ⊢",
                        "      first | linear_combination "
                        + linear_name
                        + " | nlinarith only ["
                        + linear_name
                        + "]",
                    ]
                )
                step_proofs[variable] = proof_name
                step_indices[variable] = step_number

    final_proofs: dict[sp.Expr, str] = {}
    for variable, final_expression in result.reconstruction:
        if variable not in step_proofs:
            raise LeanExportError("reconstruction variable has no defining step")
        proof_name = f"hRec_{printer.symbol(variable)}"
        later_names = [
            name
            for later_variable, name in step_proofs.items()
            if step_indices[later_variable] > step_indices[variable]
        ]
        lines.append(
            f"    have {proof_name} : {printer.symbol(variable)} = "
            f"{print_expr(final_expression)} := by"
        )
        lines.extend(proof_using(step_proofs[variable], later_names))
        final_proofs[variable] = proof_name

    reduced_by_source = {
        source_index: reduced_index
        for reduced_index, source_index in enumerate(result.reduced_residual_indices)
    }
    reconstruction_map = dict(result.reconstruction)
    if result.reduced_residuals:
        for reduced_index, source_index in enumerate(result.reduced_residual_indices):
            image = result.source_residuals[source_index].subs(
                reconstruction_map, simultaneous=True
            )
            name = f"hReduced{reduced_index}"
            source_hypothesis = f"hSource{source_index}"
            lines.append(
                f"    have {name} : "
                f"{print_expr(result.reduced_residuals[reduced_index])} = 0 := by"
            )
            rec_names = list(final_proofs.values())
            lines.append(
                f"      have hImage{reduced_index} : ({print_expr(image)} = 0) := by"
            )
            lines.extend(proof_using(source_hypothesis, rec_names, indent="        "))
            lines.extend(proof_using(f"hImage{reduced_index}"))

    if len(result.reduced_residuals) > 1:
        reduced_proof = (
            "⟨"
            + ", ".join(f"hReduced{i}" for i in range(len(result.reduced_residuals)))
            + "⟩"
        )
    else:
        reduced_proof = "hReduced0" if result.reduced_residuals else "True.intro"
    if len(final_proofs) > 1:
        reconstruction_proof = "⟨" + ", ".join(final_proofs.values()) + "⟩"
    else:
        reconstruction_proof = (
            next(iter(final_proofs.values())) if final_proofs else "True.intro"
        )
    lines.append(f"    refine ⟨{reduced_proof}, {reconstruction_proof}⟩")

    lines.append("  · intro hTarget")
    lines.append("    rcases hTarget with ⟨hReduced, hReconstruction⟩")
    if len(result.reduced_residuals) > 1:
        lines.append(
            "    rcases hReduced with "
            + "⟨"
            + ", ".join(f"hReduced{i}" for i in range(len(result.reduced_residuals)))
            + "⟩"
        )
    elif result.reduced_residuals:
        lines.append("    have hReduced0 := hReduced")
    if len(final_proofs) > 1:
        lines.append(
            "    rcases hReconstruction with "
            + "⟨"
            + ", ".join(
                f"hRec_{printer.symbol(variable)}"
                for variable, _ in result.reconstruction
            )
            + "⟩"
        )
    elif final_proofs:
        variable = result.reconstruction[0][0]
        lines.append(f"    have hRec_{printer.symbol(variable)} := hReconstruction")

    for source_index in range(len(result.source_residuals)):
        lines.append(
            f"    have hSource{source_index} : {source_equations[source_index]} := by"
        )
        if final_proofs:
            lines.append(
                "      try simp only [" + ", ".join(final_proofs.values()) + "]"
            )
            lines.append("      all_goals try norm_num")
        target_index = reduced_by_source.get(source_index)
        if has_exp:
            lines.append(f"      all_goals try simp only [{exp_rules}]")
        if target_index is None:
            lines.append(
                "      all_goals (try simp) <;> field_simp "
                + _tactic_conditions(condition_names)
                + " "
                "<;> norm_num <;> (try ring_nf) <;> ring"
            )
        else:
            reduced_hypothesis = (
                f"hReduced{target_index}"
                if len(result.reduced_residuals) != 1
                else "hReduced0"
            )
            lines.extend(proof_using(reduced_hypothesis))

    if len(source_equations) > 1:
        lines.append(
            "    exact ⟨"
            + ", ".join(f"hSource{i}" for i in range(len(source_equations)))
            + "⟩"
        )
    elif source_equations:
        lines.append("    exact hSource0")
    else:
        lines.append("    trivial")
    lines.append("#print axioms reduction_equivalence")
    return "\n".join(lines) + "\n"
