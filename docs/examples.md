# Examples and expected results

Algebraic snippets using `from equireduce ...` work in `0.1.0.dev0`.
Snippets importing only SymPy can also run directly to check mathematical
identities. They do not replace Lean proofs.

## Algebraic elimination

Input:

$$ay-x=0,\qquad y+x-1=0,\qquad a\ne0.$$

Selecting $y$ for elimination:

$$H(x,a)=x/a+x-1=0,\qquad y=x/a.$$

Intended usage:

```python
import sympy as sp
from equireduce import System, reduce_system

x, y, a = sp.symbols("x y a", real=True)
system = System.algebraic(
    residuals=(a*y - x, y + x - 1),
    unknowns=(x, y),
    parameters=(a,),
    conditions=(sp.Ne(a, 0),),
)
result = reduce_system(system, candidates=(y,), proof="none")
```

Independent forward check in SymPy:

```python
import sympy as sp

x, y, a = sp.symbols("x y a", real=True)
reconstruction = {y: x/a}
source = sp.Matrix([a*y - x, y + x - 1])
expected = sp.Matrix([0, x/a + x - 1])
assert (source.subs(reconstruction) - expected).applyfunc(sp.cancel).is_zero_matrix
```

This code checks the identity after reconstruction. The reverse direction
also needs to derive $y=x/a$ from the source row under $a\ne0$;
the certificate and Lean theorem must cover it.

## Degenerate branch

For $ay-b=0$, the result $y=b/a$ must include $a\ne0$.
If that condition was absent from the input, `coverage` must be `conditional`
until coverage of the remaining cases is proved. When $a=b=0$, $y$ is free.

## Preserving the nonlinear core

$$y-x^2=0,\qquad \exp(y)+x-c=0.$$

Reduction:

$$\exp(x^2)+x-c=0,\qquad y=x^2.$$

The library need not solve the transcendental equation. Substitution preserves
the exponential's dependence on the eliminated variable. A user-defined
function $f(y)$ follows the same rule: $f(x^2)$, not a new independent constant.

## Affine block

$$u+v-a=0,\qquad u-v-b=0,\qquad u^2+v-c=0.$$

The first two rows have determinant $-2$, so

$$u=(a+b)/2,\qquad v=(a-b)/2.$$

A parameter constraint remains:

$$((a+b)/2)^2+(a-b)/2-c=0.$$

Zero output unknowns does not mean that every equation holds.
The parameter residual must not be discarded.

## DAE without a derivative of the eliminated variable

$$\dot x+y=0,\qquad y-x^2=0.$$

The implemented API and executable Lean example are in the [DAE contract](dae.md).
The 4 → 3 and 14 → 3 examples are described in [coordinate reduction](coordinates.md).

Expected result:

$$\dot x+x^2=0,\qquad y=x^2.$$

Initial data must satisfy $y_0=x_0^2$. Equivalence is established on an
interval where the trajectory is admissible. This is an implemented
experimental DAE class.

## Substituting the eliminated variable's derivative

$$\dot x+\dot y+y=0,\qquad y-x^2=0.$$

When $x$ is differentiable:

$$\dot y=2x\dot x,\qquad (1+2x)\dot x+x^2=0.$$

The final implicit residual does not require division by $1+2x$.
Writing $\dot x=-x^2/(1+2x)$ requires the **new** condition $1+2x\ne0$.
These are different transformations with different validity conditions.
`substitute_reconstructed_rates` performs this substitution on the rational
reconstruction graph and returns conditions. It does not perform the subsequent
division or automatically solve the implicit equation for $\dot x$.

SymPy chain-rule check:

```python
import sympy as sp

t = sp.Symbol("t", real=True)
x = sp.Function("x", real=True)(t)
y_reconstructed = x**2
source_after_reconstruction = sp.diff(x, t) + sp.diff(y_reconstructed, t) + y_reconstructed
expected = (1 + 2*x)*sp.diff(x, t) + x**2
assert sp.expand(source_after_reconstruction - expected) == 0
```

## Dnipro migration acceptance example

The structural BJT system 14 → 4 is a regression example. After extraction,
the 14 source residuals, four reduced residuals, reconstruction formulas for
10 variables, and nonzero conditions must agree. A new Lean compilation of
the new pipeline's result is required; the old log does not automatically
validate the extracted implementation.

Separate kinematic-constraint and algebraic flow-balance examples are added
without Dnipro imports to establish independence from electronics.
