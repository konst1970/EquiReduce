"""Shared exact rational HasDerivAt proof construction."""

from functools import reduce

import sympy as sp

from equireduce.errors import UnsupportedExpressionError


def rational_derivative_proofs(
    expressions,
    *,
    time,
    xs,
    velocities,
    render,
    current,
    nearby,
    clock,
    sample,
    guard_names,
    rate_proofs=None,
    prefix="",
    smooth_functions=(),
    smooth_hypotheses=(),
):
    lines = []
    rate_proofs = rate_proofs or [f"hRate{i}" for i in range(len(xs))]
    memo: dict[sp.Expr, str] = {}

    def derive(expression):
        if expression in memo:
            return memo[expression]
        if expression == time:
            return f"(hasDerivAt_id {clock})"
        if expression in xs:
            return rate_proofs[xs.index(expression)]
        if not expression.has(time, *xs):
            return f"(hasDerivAt_const {clock} ({render(expression, current)}))"
        if expression.func is sp.exp:
            proof = f"({derive(expression.args[0])}).exp"
        elif any(expression.func == v.function for v in smooth_functions):
            index = next(
                i
                for i, v in enumerate(smooth_functions)
                if expression.func == v.function
            )
            parts = [derive(v) for v in expression.args]
            arguments = " ".join(f"({render(v, current)})" for v in expression.args)
            application = f"({smooth_hypotheses[index]} {arguments})"
            proof = (
                f"{application}.comp {clock} ({parts[0]})"
                if len(parts) == 1
                else f"{application}.comp_hasDerivAt {clock} "
                f"(({parts[0]}).prodMk ({parts[1]}))"
            )
        elif isinstance(expression, sp.Add | sp.Mul):
            terms = [derive(arg) for arg in expression.args]
            op = "add" if expression.is_Add else "mul"
            proof = reduce(
                lambda left, right: f"HasDerivAt.{op} ({left}) ({right})", terms
            )
        elif isinstance(expression, sp.Pow) and expression.exp.is_Integer:
            base, exponent = expression.base, int(expression.exp)
            proof = f"({derive(base)}).pow {abs(exponent)}"
            if exponent < 0:
                nonzero = f"h{prefix}Nonzero{len(memo)}"
                lines.extend(
                    [
                        f"  have {nonzero} : {render(base, current)} ≠ 0 := by",
                        "    exact Real.exp_ne_zero _"
                        if base.func is sp.exp
                        else "    first | assumption | (intro hZero; "
                        + "first "
                        + " ".join(
                            f"| (apply {guard}; nlinarith only [hZero])"
                            for guard in guard_names
                        )
                        + ")"
                        if guard_names
                        else "    norm_num",
                    ]
                )
                proof = f"({proof}).inv (pow_ne_zero {abs(exponent)} {nonzero})"
        else:
            raise UnsupportedExpressionError("unproved reconstruction derivative")
        extended = bool(smooth_functions) or expression.has(sp.exp)
        if extended:
            from equireduce.smooth import derivative as smooth_derivative

            derivative = smooth_derivative(
                expression,
                {time: sp.S.One, **dict(zip(xs, velocities, strict=True))},
                smooth_functions,
            )
        else:
            derivative = sp.diff(expression, time) + sum(
                sp.diff(expression, x) * v for x, v in zip(xs, velocities, strict=True)
            )
        name = f"h{prefix}Chain{len(memo)}"
        simplifications = (
            "id_eq, Pi.inv_apply, Pi.pow_apply, Pi.mul_apply, Pi.add_apply"
        )
        if extended:
            simplifications += ", Function.comp_apply"
        extra = (
            (
                "(try simp [neg_one_mul, Real.exp_add, "
                "Real.exp_sub, Real.exp_neg]) <;> "
                if smooth_functions
                else "(try simp only [neg_one_mul, Real.exp_add, "
                "Real.exp_sub, Real.exp_neg]) <;> "
            )
            if extended
            else ""
        )
        lines.extend(
            [
                f"  have {name} : HasDerivAt (fun {sample} : ℝ => "
                f"{render(expression, nearby)}) ({render(derivative, current)}) "
                f"{clock} := by",
                "    refine HasDerivAt.congr_of_eventuallyEq "
                f"(({proof}).congr_deriv ?_) ?_",
                f"    · (try simp only [{simplifications}]) <;> "
                + extra
                + "(try field_simp ["
                + ", ".join(guard_names)
                + "]) <;> ring",
                "    · apply Filter.Eventually.of_forall",
                f"      intro {sample}",
                f"      (try simp only [{simplifications}]) <;> "
                + ("(try simp) <;> " if extended else "")
                + "ring",
            ]
        )
        memo[expression] = name
        return name

    chain_proofs = [derive(phi) for phi in expressions]
    return lines, chain_proofs
