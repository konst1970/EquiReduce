"""A static geometric constraint coupled to an algebraic force law."""

import sympy as sp

from equireduce import System, reduce_system


def make_system():
    displacement, extension, force = sp.symbols(
        "displacement extension force", real=True
    )
    stiffness = sp.Symbol("stiffness", real=True)
    return System.algebraic(
        (extension - displacement**2, force - stiffness * extension),
        (displacement, extension, force),
        parameters=(stiffness,),
    ), (extension,)


if __name__ == "__main__":
    system, candidates = make_system()
    result = reduce_system(system, candidates=candidates)
    print(result.reduced_system.residuals)
    print(dict(result.reconstruction))
