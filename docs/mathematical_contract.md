# Mathematical contract

## Input system and domain of definition

The algebraic input is

$$
F(X,p)=0,\qquad X\in\mathbb R^n,\quad p\in\mathbb R^k,
$$

where each component of $F$ is an equation residual. A separate predicate
$D_F(X,p)$ specifies the domain and assumptions: nonzero denominators,
signs of logarithm arguments, and valid parameters and branches.
The number of equations need not equal the number of unknowns.

Symbols, parameters, and equation order are explicit. The formal interpretation
of the first release is real arithmetic; complex assumptions must not be
silently ignored. All additional assumptions appear in the result and Lean
statement.

## The result as a correspondence between solution sets

Let $Z$ be the retained coordinates, $P:X\mapsto Z$ a projection or coordinate
map, and $R:Z\mapsto X$ the full reconstruction. The result contains
$H(Z,p)=0$ and the conditions $C(Z,p)$ under which elimination is valid.

Define

$$
D_R(Z,p)=C(Z,p)\land D_F(R(Z,p),p).
$$

The target statement is

$$
\begin{aligned}
&F(X,p)=0\land D_F(X,p)\land C(P(X,p),p)\\
&\quad\iff
\exists Z:\ H(Z,p)=0\land D_R(Z,p)\land X=R(Z,p).
\end{aligned}
$$

On valid reduced solutions, $P(R(Z,p),p)=Z$ is also checked. This establishes
mutual recovery rather than only necessity of the reduced equations. For
ordinary elimination, $P$ selects retained variables and
$R(Z,p)=(Z,\varphi(Z,p))$ in the source order.

Separate certificates for coordinate changes and elimination can be composed,
but the final statement must cover the source and final systems and all
accumulated conditions.

## Conditional reduction and completeness

If elimination requires $a\ne0$, the library must not claim global equivalence
for $a=0$. Only the following outcomes are valid:

1. The user's assumptions already imply $a\ne0$, with justification.
2. A conditional result is returned with the explicit additional restriction $a\ne0$.
3. The branches $a\ne0$ and $a=0$ are handled separately with a coverage proof.
4. The step is skipped because justification is unavailable.

The first release must support outcomes two and four. Automatically splitting
all degenerate cases is not a requirement.
`coverage="conditional"` means solutions outside the conditions have not been
examined. A successful Lean proof of a conditional theorem does not change
this to `coverage="complete"`.

For example, $ay-b=0$ gives $y=b/a$ when $a\ne0$. When $a=0$, $b=0$,
any $y$ is allowed; when $a=0$, $b\ne0$, there are no solutions.
Neither branch may be silently discarded.

## Exactness and partial functions

- `Integer` and `Rational` are transferred exactly, without automatic rounding.
- `Float` is rejected by default. Explicit `exact_decimal` mode interprets the
  object's decimal representation as an exact rational number; it does not
  recover precision already lost in the source data.
- Cancelling a fraction does not remove the original exclusion of denominator zeros.
- Lean uses total operations over $\mathbb R$, including division. Without domain
  predicates, their semantics differ from those of partial mathematical
  expressions; the required conditions must appear in the theorem.
- `Piecewise` preserves branch order and exact conditions. An incomplete set of
  branches requires an explicit coverage domain or rejection as unsupported.

SymPy may simplify an expression before it reaches the library: for example,
`x/x` can become `1`. The lost condition $x\ne0$ cannot reliably be recovered
from the constant. The input adapter must supply it separately or preserve
the source structure until normalization.

## Uncertainty and inconsistency

A SymPy answer of "unknown" does not prove zero, nonzero, or invertibility.
Exact identity recognition has at least three outcomes:
`zero`, `not_identically_zero`, and `unknown`.
"Not identically zero" does not mean "never zero".

Contradictory conditions can make a theorem vacuously true. Assumption
consistency is therefore reported separately as `consistent`, `inconsistent`,
or `unknown`. Formal proof status alone does not establish existence of a
solution or a nonempty domain.

## What Lean establishes

Lean checks the generated statement under its explicit assumptions.
This does not establish correspondence between the source equations and a
physical object, measured parameter quality, or correctness of an independent
adapter. The mapping from SymPy expressions to Lean expressions is part of
the exporter's trusted boundary and needs separate tests and a specification.
