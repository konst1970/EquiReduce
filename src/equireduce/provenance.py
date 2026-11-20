"""Portable source labels whose rename is checked against the certificate input."""

from collections.abc import Mapping
from types import MappingProxyType

import sympy as sp

from equireduce.errors import CertificateError
from equireduce.smooth import raw_replace


def freeze(value):
    if isinstance(value, Mapping):
        return MappingProxyType({k: freeze(v) for k, v in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(freeze(v) for v in value)
    return value


def verify_provenance(source, value):
    if value is None:
        return
    if not isinstance(value, Mapping) or value.get("schema") != "time-source/v1":
        raise CertificateError("unsupported source provenance")
    try:
        mapping = dict(value["symbol_map"])
        originals = (*value["unknowns"], *value["parameters"], *value["inputs"])
        if set(mapping) != set(originals):
            raise CertificateError(
                "source rename must cover exactly its declared labels"
            )
        for item in (*value["unknowns"], *value["inputs"]):
            if not isinstance(item, sp.core.function.AppliedUndef) or item.args != (
                source.time,
            ):
                raise CertificateError("original states/inputs must be time functions")
        if any(not isinstance(v, sp.Symbol) for v in value["parameters"]):
            raise CertificateError("original parameters must be symbols")
        if any(v.is_real is False for v in originals):
            raise CertificateError("original source cannot be complex")
        if value["real_domain_assumed"] != any(
            v.is_real is not True for v in originals
        ):
            raise CertificateError("original real-domain policy mismatch")
        if len(mapping) != len(value["symbol_map"]) or len(
            set(mapping.values())
        ) != len(mapping):
            raise CertificateError("source rename must be injective")
        pairs = (
            ("unknowns", source.unknowns),
            ("parameters", source.parameters),
            ("inputs", source.inputs),
            ("residuals", source.residuals),
            ("conditions", source.conditions),
            ("interval", source.interval),
        )
        if any(
            tuple(raw_replace(v, mapping) for v in value[key]) != expected
            for key, expected in pairs
        ):
            raise CertificateError(
                "source provenance does not match the certified input"
            )
        if (
            value["time"] != source.time
            or tuple(value["residual_names"]) != source.residual_names
        ):
            raise CertificateError("source clock/row labels mismatch")
        if (
            tuple((raw_replace(v, mapping), i) for v, i in value["branch_choices"])
            != source.branch_choices
        ):
            raise CertificateError("source branch provenance mismatch")
        if any(not isinstance(v, sp.Basic) for v in mapping):
            raise CertificateError("invalid source labels")
    except (KeyError, TypeError, AttributeError, ValueError) as exc:
        raise CertificateError(f"invalid source provenance: {exc}") from exc
