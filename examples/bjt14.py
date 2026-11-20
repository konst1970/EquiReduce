"""Neutral SymPy fixture for the 14 -> 4 MNA structural regression."""

import sympy as sp

from equireduce import System


def make_system(*, voltage_differences=False):
    variables = sp.symbols(
        "vs vd vb vc jin jCC jC jB jE jepi vbi vci vei vx", real=True
    )
    vs, vd, vb, vc, jin, jcc, jc, jb, je, jepi, vbi, vci, vei, vx = variables
    parameters = sp.symbols("Uin Ucc Rs Rl rC rE Rco", real=True)
    uin, ucc, rs, rl, rc, re, rco = parameters
    ib, ic, ie, rb, drive = (
        sp.Function(name)(vbi, vci, vei, vx) for name in ("Ib", "Ic", "Ie", "rB", "D")
    )
    if voltage_differences:
        ib, ic, ie, rb = (
            sp.Function(name)(vbi - vei, vbi - vci) for name in ("Ib", "Ic", "Ie", "rB")
        )
        drive = sp.Function("D")(vbi - vci, vbi - vx)
    rows = (
        (vs - vb) / rs + jin,
        (vd - vc) / rl + jcc,
        (vb - vs) / rs + jb,
        (vc - vd) / rl + jc,
        jepi - jc,
        ib - jb,
        ie - je,
        ic - jepi,
        vs - uin,
        vd - ucc,
        vc - vx - rc * jc,
        vb - vbi - rb * jb,
        -vei - re * je,
        drive - rco * jepi,
    )
    return System.algebraic(rows, variables, parameters=parameters), variables[:10]
