"""Algebraic flow balance with a nonlinear measurement equation."""

import sympy as sp

from equireduce import System, reduce_system


def make_system():
    left, right, measurement = sp.symbols("left right measurement", real=True)
    inflow, ratio = sp.symbols("inflow ratio", real=True)
    return System.algebraic(
        (inflow - left - right, left - ratio * right, measurement - left**2),
        (left, right, measurement),
        parameters=(inflow, ratio),
        conditions=(sp.Ne(ratio + 1, 0),),
    ), (left, right)


if __name__ == "__main__":
    system, candidates = make_system()
    result = reduce_system(system, candidates=candidates)
    print(result.reduced_system.residuals)
    print(dict(result.reconstruction))
