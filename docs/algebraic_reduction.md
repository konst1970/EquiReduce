# Algebraic reduction algorithms

## Processing sequence

1. Validate types, unknown order, parameters, domains, and numeric exactness.
2. Keep an immutable snapshot of the input and conditions before transformation.
3. Identify variables and blocks in which the residuals are affine.
4. Construct an elimination candidate and every required condition.
5. Substitute reconstruction formulas, updating remaining equations and the step trace.
6. Independently verify the candidate certificate.
7. Compare admissible results using the chosen objective.
8. Generate or compile a Lean proof when requested.

Normalization must be conservative: avoid expanding arbitrarily large products
or applying transformations that require unrecorded assumptions. Search time
and expression sizes are bounded by budgets.

## Scalar affine step

A row has the form

$$a(Z,p)y+b(Z,p)=0.$$

When $a\ne0$, $y=-b/a$. The coefficients must be independent of $y$;
this must be checked rather than inferred from the expression's appearance.
Substitute the formula into every remaining equation.
Every previously eliminated variable must eventually have a reconstruction
using only final coordinates and parameters, without cyclic dependencies.
Conditions from earlier steps are also transported through all subsequent
substitutions. If reconstruction makes a condition false, the candidate
cannot be treated as an admissible nonempty branch. If its truth is unknown,
the obligation remains explicit.

## Block elimination

For selected rows and variables:

$$A(Z,p)Y+b(Z,p)=0,\qquad \det A(Z,p)\ne0.$$

Return the exact block solution $Y=\varphi(Z,p)$. The implementation may use
exact linear solving without explicitly computing an inverse matrix.
Nonzero assumptions for denominators introduced by the algorithm are checked
separately; a symbolic rank estimate does not remove the need for conditions.

A singular, rectangular, or undetermined block must not be treated as an
ordinary invertible square block. The first release skips such a candidate
or selects a certified square subblock. Remaining equations are not removed
without proof of redundancy.

## Nonlinear functions

Exponentials, logarithms, and other nonlinear dependencies can remain in the
residual core. If an affine step is valid for any function $f(Z)$, its physical
formula need not be proved.

However, replacing $f(y)$ with a new independent symbol must not allow $y$
to be eliminated while losing the function's dependence on $y$. Every function
occurrence must receive the exact argument substitution after reconstruction.

## Coordinate changes

The initial supported class is $X=M U+c$ with an exact inverse matrix and
conditions $\det M\ne0$. The matrix and offset may depend on parameters
but not unknowns. Both maps are checked by a separate certificate; this
does not permit arbitrary nonlinear coordinate changes.

Automatic search starts with the identity, permutations, simple integer linear
combinations, and sum/difference bases. The coefficient bound and candidate
count are parameters rather than hidden heuristics.

## Certificate and independent verification

For each step, record source rows, pivot coefficients, conditions, the
elimination formula, substitutions, and the link to the next system.
For linear row combinations, matrices $Q,T$ may additionally be constructed
with identities $F=QG$, $G=TF$. Requiring both matrices is not universal for
arbitrary nonlinear substitutions; the general contract is defined by a
bidirectional statement and reconstruction.

The verifier does not repeat the search for the best candidate: it takes a
completed certificate and checks every claimed step against the immutable
input. An unconfirmed identity yields `unknown` or `failed`, not success.

## Optimization criteria

The initial deterministic ranking is lexicographic:

1. Fewer unknowns.
2. Lower estimated complexity of the reduced Jacobian.
3. Smaller expression trees and DAGs.
4. Fewer new conditions and lower coordinate transformation cost.
5. Estimated formal proof complexity and stable candidate order.

An estimated Lean operation count is not measured compilation time.
Timing comparisons require a fixed environment with the same cache warm-up
and repetition rules. Extended objectives must be explicitly available
without changing the mathematical contract.

## Termination

The result records the termination reason: no supported steps, budget reached,
a contradiction found, or completion of the declared candidate family.
No reduction is a valid result with identity reconstruction.
`search_complete` applies only to the declared finite family, not to all
possible mathematical transformations.
