# Terminology and notation

| Term | Meaning in EquiReduce |
|---|---|
| Equation residual | Expression $F_i$ defining the equation $F_i=0$ |
| Reduction | Exact transformation preserving the stated solution correspondence |
| Simplification | Optimization of a chosen metric; not necessarily a shorter printed expression |
| Unknown | A coordinate whose value must satisfy the system |
| Parameter | An explicitly declared quantity that is not eliminated and is constant in time in a DAE |
| Affinity in $Y$ | Representation $A(Z,p)Y+b(Z,p)$ with coefficients independent of $Y$ |
| Reconstruction | Formulas recovering all source variables from final coordinates |
| Domain of definition | Conditions under which source expressions have the required mathematical meaning |
| Step condition | Assumption required by a particular elimination or transformation |
| Conditional reduction | Equivalence proved only on an explicitly restricted part of the domain |
| Certificate | Data and witnesses sufficient to check a transformation |
| Symbolic verification | Identity checks in a CAS, here SymPy |
| Formal verification | Acceptance of a specific Lean theorem with allowed dependencies |
| Artifact | Versioned portable bundle of input, result, and evidence |
| Run report | Information about a particular tool invocation |
| AST | Expression tree with explicitly defined node types |
| DAG | Expression graph with shared subexpressions |
| DAE | Differential-algebraic equation system |
| Classical trajectory | Functions of specified regularity satisfying the equations on an interval |
| Consistent initial data | Data satisfying the algebraic and necessary differential constraints |
| Differential index | A measure of required constraint differentiation; not the number of written derivatives |
| Toolchain | Pinned set of formal tool versions |

Notation: $X$ — source coordinates; $Z$ — final coordinates;
$Y$ — eliminated coordinates; $p$ — parameters; $F$ — source residuals;
$H$ — reduced residuals; $P$ — projection; $R$ — full reconstruction;
$\varphi$ — formulas for eliminated variables; $C$ — step conditions;
$D_F$ — source system domain; $I$ — time interval.
