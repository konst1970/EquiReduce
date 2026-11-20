"""BJT-shaped structural regressions with explicit voltage-difference dependence.

The device functions are arbitrary real functions. No constitutive BJT law is
asserted by this fixture. The default four-argument bjt14 fixture deliberately
keeps its weaker assumptions and still only reduces to four unknowns.
"""

import sympy as sp

from equireduce import AffineTransform, System

from . import bjt14


def voltage_matrix():
    return sp.ImmutableMatrix(
        ((1, 0, 0, 1), (1, -1, 0, 1), (0, 0, 0, 1), (1, 0, -1, 1))
    )


def make_system():
    vbi, vci, vei, vx = sp.symbols("vbi vci vei vx", real=True)
    params = sp.symbols("Uin Ucc Rs Rl rC rE Rco", real=True)
    uin, ucc, rs, rl, rc, re, rco = params
    ube, ubci, ubcx, emitter = sp.symbols("ube ubci ubcx emitter", real=True)
    ib, ic, ie, rb = (
        sp.Function(name)(vbi - vei, vbi - vci) for name in ("Ib", "Ic", "Ie", "rB")
    )
    drive = sp.Function("D")(vbi - vci, vbi - vx)
    source = System.algebraic(
        (
            vei + re * ie,
            vbi - uin + (rs + rb) * ib,
            vx - ucc + (rl + rc) * ic,
            drive - rco * ic,
        ),
        (vbi, vci, vei, vx),
        parameters=params,
    )
    transform = AffineTransform.create(
        source,
        variables=(ube, ubci, ubcx, emitter),
        matrix=voltage_matrix(),
    )
    return source, transform, (emitter,)


def make_full_system():
    source, _ = bjt14.make_system(voltage_differences=True)
    linear = sp.symbols(
        "s_vs s_vd s_vb s_vc s_jin s_jCC s_jC s_jB s_jE s_jepi", real=True
    )
    ube, ubci, ubcx, emitter = sp.symbols("ube ubci ubcx emitter", real=True)
    transform = AffineTransform.create(
        source,
        variables=linear + (ube, ubci, ubcx, emitter),
        matrix=sp.diag(sp.eye(10), voltage_matrix()),
    )
    return source, transform, (*linear, emitter)
