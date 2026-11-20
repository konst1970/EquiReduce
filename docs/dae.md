# Differential-algebraic systems

## Status and goal

`0.1.0.dev0` provides a separate experimental `DAESystem` / `reduce_dae` API.
It supports the semi-explicit class described below with rational
reconstruction. Lean compiles a bidirectional trajectory theorem on an open
interval and the chain rule using actual `HasDerivAt` statements.
Algebraic `System.algebraic` continues to reject derivatives.

A separate [implicit DAE pipeline](implicit_dae.md) implements DN-DAE-01–12:
the contract, time adapter, structure, algebraic reduction without mass matrix
inversion, complete Lean proof, initial data, partition search, time-dependent
coordinates, and differentiable prescribed inputs. This page describes the
semi-explicit API; the separate implicit contract covers original MNA rows
and composition of coordinate charts.

General formulation:

$$F(t,X(t),\dot X(t),p)=0.$$

Parameters $p$ are constant in time. A time-varying external signal requires
a separate function declaration and regularity assumptions; it cannot be
declared a constant parameter. Treating $X$ and $\dot X$ as independent
symbols can help structural analysis but does not prove trajectory correspondence.

## Initial supported class

The current semi-explicit DAE implementation is restricted to systems

$$
\begin{aligned}
\dot x &= f(t,x,y,p),\\
0 &= A(t,x,p)y+b(t,x,p).
\end{aligned}
$$

The algebraic block is square, exactly affine in $y$, and invertible on the
stated domain. Reconstruction must be rational in $t,x,p$. Exact predicates
and nonzero denominator conditions specify the domain. In this initial
implementation, equations contain no $\dot y$, second derivatives, or
impulsive terms.

When $\det A\ne0$:

$$y=\varphi(t,x,p),\qquad \dot x=f(t,x,\varphi(t,x,p),p).$$

Nonsingularity of $\partial g/\partial y=A$ gives the standard local index-1
structure. The library must not assign this conclusion to an arbitrary DAE
merely because it contains some affine row.

## Equivalence on an interval

For an open interval $I$, prove:

1. If $(x(t),y(t))$ is an admissible classical trajectory of the source DAE
   on $I$, then $x(t)$ satisfies the reduced system.
2. If $x(t)$ satisfies the reduced system and all reduction conditions hold
   for every $t\in I$, then $y(t)=\varphi(t,x(t),p)$ reconstructs an
   admissible source trajectory.
3. Reconstruction preserves the required regularity class and initial conditions.

The implemented contract requires differentiability of $x,y$ at every point
of the open interval. The formal proof derives differentiability of $y$
from its rational formula and the derivatives of $x$. Continuity of the
derivative as a separate $C^1$ property is not currently claimed by the
backend. This refines the ER-16–ER-18 contract.
This is a correspondence proof for existing solutions. Existence, uniqueness,
and extension to interval boundaries do not follow automatically.

The condition $\det A\ne0$ must hold along the entire trajectory on $I$.
Checking only the initial time is insufficient. When a singular boundary is
reached, the result no longer promises equivalence beyond it.

## Implemented transport of first derivatives

For rational reconstruction, the chain rule is computed and proved:

$$
\dot y=\frac{\partial\varphi}{\partial t}
        +\frac{\partial\varphi}{\partial x}\dot x.
$$

For $y=x^2$, this gives $\dot y=2x\dot x$.
`result.reconstruction_derivatives` contains exact expressions with
`Derivative(x(t), t)`. The theorem `reconstructed_rate_equivalence` establishes
the derivatives of an arbitrary trajectory $y$ agreeing with reconstruction
on the interval. It uses local equality of functions on an open neighborhood,
not equality at a single point.

`result.substitute_reconstructed_rates(residuals)` returns `RateSubstitution`:
new residuals, conditions, and the DAE graph certificate.
`verify_rate_substitution` independently checks substitution and the domains
of additional expressions before possible pole cancellation. This is
substitution on a proved graph; it does not solve a new arbitrary implicit
DAE. The `semi_explicit` input still forbids derivatives in the right-hand
side or algebraic block.

If $\varphi$ depends on $\dot x$, differentiation introduces $\ddot x$;
such steps are outside the supported class and are rejected.

A differential coordinate change $X=M(t)U+c(t)$ must account for
$\dot X=M\dot U+\dot M U+\dot c$. An algebraic coordinate certificate
therefore cannot be reused as a complete DAE proof.

## Initial conditions

For specified $t_0,x_0,y_0$, check

$$y_0=\varphi(t_0,x_0,p),\qquad g(t_0,x_0,y_0,p)=0.$$

Undetermined initial conditions produce symbolic obligations.
Known inconsistent conditions are rejected rather than corrected by the
library. If the user supplies no initial data, the result must state that
trajectory correspondence was proved without checking a specific initial
value problem.

## Limits and counterexamples

- **High index.** $\dot x-y=0$, $x=0$: the constraint implies $\dot x=0$,
  hence $y=0$. Removing $x=0$ after substitution is insufficient.
- **Missing branch.** $y^2=x$: selecting $y=\sqrt x$ loses the negative
  branch unless the user restricts $y\ge0$.
- **Nonsmooth reconstruction.** $y=|x|$: a classical derivative does not
  exist when crossing $x=0$ without additional conditions.
- **Incorrect differentiation.** Differentiating $x^2-1=0$ gives
  $2x\dot x=0$, but the latter permits extra constant trajectories without
  the original constraint.

This semi-explicit API does not support nonrational reconstruction, automatic
reduction of arbitrary index, branch switching, jump events, distributional
solutions, PDEs, or approximate elimination of fast states. The library
contains no numerical integrator.

## Separate DAE certificate requirements

Beyond the algebraic trace, record the independent variable, state partition,
interval and domain, regularity assumptions, reconstruction derivatives,
initial data correspondence, and formal trajectory theorem.
`verify_dae_certificate` replays the algebraic trace and independently
recomputes reconstruction, right-hand sides, conditions, and first derivatives.
The JSON artifact retains actual time functions and derivatives; loading also
checks initial data.

## Executable example

```python
import sympy as sp
from equireduce import DAESystem, reduce_dae

t = sp.Symbol("t", real=True)
x, y = (sp.Function(name, real=True)(t) for name in ("x", "y"))
system = DAESystem.semi_explicit(
    time=t, differential=(x,), algebraic=(y,),
    rhs=(-y,), constraints=(y-x**2,), interval=(-1, 1),
)
result = reduce_dae(system, initial_time=0, initial_values={x: 2, y: 4})
assert result.reconstruction[y] == x**2
assert result.reduced_residuals == (sp.diff(x,t) + x**2,)
assert result.initial_check.status == "verified"
```

State functions are declared with `real=True`; parameters are separate constant
real symbols. Interval endpoints are finite and exact. For symbolic endpoints,
`system.interval_condition` is an additional nonemptiness obligation.
The Lean theorem includes this premise explicitly.

When supplied, initial data must cover every state, with time inside the open
interval. `initial_check` has status `not_provided`, `verified`, or `conditional`
with remaining symbolic obligations. This is an exact symbolic check of specific
data; the formal trajectory theorem applies at every interval point, including
the initial point.

Complete example with actual compilation and an artifact:

```bash
.venv/bin/python -m examples.dae_first_order
```
