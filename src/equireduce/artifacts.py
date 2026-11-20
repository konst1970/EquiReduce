"""Versioned JSON AST serialization; no executable expression parser."""

from __future__ import annotations

import hashlib
import json
import math
import platform
from collections.abc import Mapping
from dataclasses import fields, is_dataclass, replace
from enum import Enum
from importlib.resources import files
from pathlib import Path

import sympy as sp

from equireduce import _core
from equireduce._version import __version__
from equireduce.api import _from_core, verify_certificate
from equireduce.coordinates import AffineTransform, _from_coordinate_certificate
from equireduce.dae import (
    DAECertificate,
    DAEReductionResult,
    DAESystem,
    InitialCheck,
    _from_dae_certificate,
    verify_dae_certificate,
)
from equireduce.dae_structure import (
    DerivativeNormalization,
    ImplicitDAEStructure,
    SymbolicRank,
)
from equireduce.errors import ArtifactError, CertificateError
from equireduce.implicit import ImplicitDAESystem
from equireduce.implicit_initial import ImplicitInitialCheck
from equireduce.implicit_reduction import (
    ImplicitDAEReductionResult,
    ImplicitReductionCertificate,
)
from equireduce.implicit_search import ImplicitPartitionReport, PartitionCandidate
from equireduce.metrics import ComplexityMetrics
from equireduce.result import (
    Certificate,
    CoordinateCertificate,
    FormalCheck,
    ProofStatus,
    ReductionResult,
)
from equireduce.search import CandidateSummary, SearchReport
from equireduce.smooth import SmoothFunction
from equireduce.system import System
from equireduce.time_coordinates import (
    ImplicitCoordinateCertificate,
    TimeAffineTransform,
)

SCHEMA = "equireduce.reduction/v1"
IMPLICIT_SCHEMA = "equireduce.implicit/v1"
RECORDS = {
    "ImplicitSystem": ImplicitDAESystem,
    "ImplicitResult": ImplicitDAEReductionResult,
    "ImplicitCertificate": ImplicitReductionCertificate,
    "ImplicitCoordinateCertificate": ImplicitCoordinateCertificate,
    "TimeAffineTransform": TimeAffineTransform,
    "ImplicitInitialCheck": ImplicitInitialCheck,
    "DerivativeNormalization": DerivativeNormalization,
    "ImplicitStructure": ImplicitDAEStructure,
    "SymbolicRank": SymbolicRank,
    "PartitionCandidate": PartitionCandidate,
    "ImplicitPartitionReport": ImplicitPartitionReport,
    "SmoothFunction": SmoothFunction,
    "DAESystem": DAESystem,
    "DAECertificate": DAECertificate,
    "DAEResult": DAEReductionResult,
    "InitialCheck": InitialCheck,
    "ComplexityMetrics": ComplexityMetrics,
    "CandidateSummary": CandidateSummary,
    "SearchReport": SearchReport,
    "System": System,
    "Result": ReductionResult,
    "Certificate": Certificate,
    "CoordinateCertificate": CoordinateCertificate,
    "AffineTransform": AffineTransform,
    "CoreResult": _core.ReductionResult,
    "Step": _core.ReductionStep,
    "Block": _core.ReductionBlockStep,
    "SymbolicCheck": _core.CertificateVerification,
    "FormalCheck": FormalCheck,
}
ENUMS = {
    "ProofStatus": ProofStatus,
    "CertificateStatus": _core.CertificateStatus,
    "AffineStatus": _core.AffineStatus,
}
FUNCTIONS = {
    name: getattr(sp, name)
    for name in (
        "Add",
        "Mul",
        "Pow",
        "Equality",
        "Unequality",
        "StrictGreaterThan",
        "GreaterThan",
        "StrictLessThan",
        "LessThan",
        "And",
        "Or",
        "Not",
        "exp",
        "log",
        "sin",
        "cos",
        "tan",
        "Abs",
        "Max",
        "Min",
    )
}


def _canonical(value) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode()


class Codec:
    def __init__(self):
        self.symbols = {}
        self.decoded_symbols = {}
        self.nodes = 0

    def encode(self, value):
        if value is sp.true or value is sp.false:
            return {"t": "boolean", "v": bool(value)}
        if isinstance(value, Enum):
            return {"t": "enum", "name": type(value).__name__, "v": value.value}
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if isinstance(value, float) and math.isfinite(value):
            return {"t": "float", "v": repr(value)}
        if isinstance(value, sp.Symbol):
            identity = self.symbols.setdefault(value, len(self.symbols))
            return {
                "t": "symbol",
                "id": identity,
                "name": value.name,
                "assumptions": value._assumptions_orig,
            }
        if isinstance(value, sp.Integer):
            return {"t": "integer", "v": str(value)}
        if isinstance(value, sp.Rational):
            return {"t": "rational", "p": str(value.p), "q": str(value.q)}
        if isinstance(value, sp.MatrixBase):
            return {
                "t": "matrix",
                "rows": value.rows,
                "cols": value.cols,
                "args": [self.encode(v) for v in value],
            }
        if isinstance(value, sp.core.function.AppliedUndef):
            return {
                "t": "function",
                "name": value.func.__name__,
                "assumptions": value.func._kwargs,
                "args": [self.encode(v) for v in value.args],
            }
        if isinstance(value, sp.Piecewise):
            return {
                "t": "piecewise",
                "pairs": [[self.encode(v), self.encode(c)] for v, c in value.args],
            }
        if isinstance(value, sp.Derivative):
            if len(value.variable_count) != 1 or value.variable_count[0][1] != 1:
                raise ArtifactError(
                    "only first-order state derivatives can be serialized"
                )
            return {
                "t": "derivative",
                "expr": self.encode(value.expr),
                "variable": self.encode(value.variable_count[0][0]),
            }
        if isinstance(value, sp.Basic) and value.func.__name__ in FUNCTIONS:
            return {
                "t": "expr",
                "name": value.func.__name__,
                "args": [self.encode(v) for v in value.args],
            }
        if is_dataclass(value):
            name = next(
                (key for key, cls in RECORDS.items() if type(value) is cls), None
            )
            if name:
                return {
                    "t": "record",
                    "name": name,
                    "fields": {
                        f.name: self.encode(getattr(value, f.name))
                        for f in fields(value)
                    },
                }
        if isinstance(value, Mapping):
            return {
                "t": "map",
                "pairs": [[self.encode(k), self.encode(v)] for k, v in value.items()],
            }
        if isinstance(value, (tuple, list)):
            return {"t": "tuple", "args": [self.encode(v) for v in value]}
        raise ArtifactError(f"unsupported artifact value: {type(value).__name__}")

    def decode(self, value, depth=0):
        self.nodes += 1
        if depth > 64 or self.nodes > 100_000:
            raise ArtifactError("artifact exceeds decoding limits")
        if value is None or isinstance(value, (str, int, bool)):
            return value
        if not isinstance(value, dict):
            raise ArtifactError("invalid AST node")
        tag = value["t"]
        if tag == "float":
            number = float(value["v"])
            if not math.isfinite(number):
                raise ArtifactError("nonfinite runtime metadata")
            return number

        def unpack(item):
            return self.decode(item, depth + 1)

        if tag == "boolean":
            return sp.true if value["v"] else sp.false
        if tag == "symbol":
            if len(value["name"]) > 256 or not all(
                isinstance(v, bool) for v in value["assumptions"].values()
            ):
                raise ArtifactError("invalid symbol declaration")
            symbol = sp.Symbol(value["name"], **value["assumptions"])
            identity = value["id"]
            prior = self.decoded_symbols.setdefault(identity, symbol)
            if prior != symbol:
                raise ArtifactError("conflicting symbol identity")
            return prior
        if tag in ("integer", "rational"):
            values = [value["v"]] if tag == "integer" else [value["p"], value["q"]]
            if any(not isinstance(v, str) or len(v) > 1000 for v in values):
                raise ArtifactError("integer exceeds decoding limits")
            numbers = [int(v) for v in values]
            if tag == "rational" and numbers[1] == 0:
                raise ArtifactError("zero rational denominator")
            return sp.Integer(numbers[0]) if tag == "integer" else sp.Rational(*numbers)
        if tag == "enum":
            return ENUMS[value["name"]](value["v"])
        if tag == "record":
            cls = RECORDS[value["name"]]
            if set(value["fields"]) != {f.name for f in fields(cls)}:
                raise ArtifactError("record fields do not match schema")
            return cls(**{key: unpack(item) for key, item in value["fields"].items()})
        if tag == "map":
            return {unpack(pair[0]): unpack(pair[1]) for pair in value["pairs"]}
        if tag == "derivative":
            expression, variable = unpack(value["expr"]), unpack(value["variable"])
            if (
                not isinstance(variable, sp.Symbol)
                or not isinstance(expression, sp.Expr)
                or expression.has(sp.Derivative)
            ):
                raise ArtifactError(
                    "derivative must be a first-order declared state rate"
                )
            return sp.Derivative(expression, variable, evaluate=False)
        if tag == "piecewise":
            return sp.Piecewise(
                *[(unpack(v), unpack(c)) for v, c in value["pairs"]], evaluate=False
            )
        args = [unpack(item) for item in value.get("args", ())]
        if tag == "tuple":
            return tuple(args)
        if tag == "matrix":
            rows, cols = value["rows"], value["cols"]
            if (
                not isinstance(rows, int)
                or not isinstance(cols, int)
                or not 0 <= rows * cols <= 100_000
            ):
                raise ArtifactError("invalid matrix dimensions")
            return sp.ImmutableMatrix(rows, cols, args)
        if tag == "function":
            if not isinstance(value["name"], str) or len(value["name"]) > 256:
                raise ArtifactError("invalid function name")
            assumptions = value.get("assumptions", {})
            if not all(isinstance(v, bool) for v in assumptions.values()):
                raise ArtifactError("invalid function assumptions")
            return sp.Function(value["name"], **assumptions)(*args)
        if tag == "expr":
            name = value["name"]
            if name == "Pow" and len(args) == 2 and isinstance(args[1], sp.Integer):
                exponent = abs(int(args[1]))
                if exponent > 10_000:
                    raise ArtifactError("power exceeds decoding limit")
                if isinstance(args[0], sp.Rational) and (
                    max(abs(int(args[0].p)).bit_length(), int(args[0].q).bit_length())
                    * exponent
                    > 100_000
                ):
                    raise ArtifactError("numeric power exceeds decoding limit")
            function = FUNCTIONS[name]
            if name in {
                "Add",
                "Mul",
                "Pow",
                "Equality",
                "Unequality",
                "StrictGreaterThan",
                "GreaterThan",
                "StrictLessThan",
                "LessThan",
            }:
                return function(*args, evaluate=False)
            return function(*args)
        raise ArtifactError(f"unsupported AST tag: {tag}")


def artifact_document(result):
    """Return the complete portable AST document without writing files."""
    payload = Codec().encode(result)
    document = {
        "schema": IMPLICIT_SCHEMA
        if isinstance(result, ImplicitDAEReductionResult)
        else SCHEMA,
        "versions": {
            "python": platform.python_version(),
            "sympy": sp.__version__,
            "equireduce": __version__,
            "exporter": "implicit-v1"
            if isinstance(result, ImplicitDAEReductionResult)
            else "dae-v1"
            if isinstance(result, DAEReductionResult)
            else "algebraic-v1",
        },
        "payload": payload,
        "sha256": hashlib.sha256(_canonical(payload)).hexdigest(),
        "mathematical_sha256": hashlib.sha256(
            _canonical(Codec().encode(result.certificate))
        ).hexdigest(),
    }
    return document


def export_artifact(
    result: ReductionResult | DAEReductionResult | ImplicitDAEReductionResult,
    path: str | Path,
) -> Path:
    """Write an exact JSON artifact or a reproducible proof directory."""
    path = Path(path)
    bundle = path.suffix != ".json"
    destination = path / "artifact.json" if bundle else path
    destination.parent.mkdir(parents=True, exist_ok=True)
    document = artifact_document(result)
    destination.write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    if bundle:
        if result.formal_check.source:
            (path / "proof.lean").write_text(result.formal_check.source)
        (path / "verification.json").write_text(
            json.dumps(
                {
                    "status": result.formal_check.status.value,
                    "origin": result.formal_check.origin,
                    "source_sha256": result.formal_check.source_sha256,
                    "axioms": result.formal_check.axioms,
                    "toolchain": result.formal_check.toolchain_version,
                    "mathlib_revision": result.formal_check.mathlib_revision,
                    "command": result.formal_check.command,
                    "seconds": result.formal_check.seconds,
                    "checked_at_utc": result.formal_check.checked_at_utc,
                },
                indent=2,
            )
            + "\n"
        )
        (path / "verification.log").write_text(result.formal_check.output)
        for name in ("lean-toolchain", "lakefile.toml", "lake-manifest.json"):
            (path / name).write_bytes(
                files("equireduce").joinpath("resources", name).read_bytes()
            )
        (path / "README.md").write_text(
            "# EquiReduce proof artifact\n\nPrepare the pinned dependencies with "
            "`MATHLIB_NO_CACHE_ON_UPDATE=1 lake update`, then `lake exe cache get`.\n\n"
            "Compile with `lake env lean -DwarningAsError=true proof.lean`.\n"
            "The JSON status records a past run; loading it does not recompile Lean.\n"
        )
    return destination


def load_artifact(
    path: str | Path,
) -> ReductionResult | DAEReductionResult | ImplicitDAEReductionResult:
    """Decode and replay the symbolic certificate; never execute stored code."""
    path = Path(path)
    if path.is_dir():
        path /= "artifact.json"
    try:
        if path.stat().st_size > 2_000_000:
            raise ArtifactError("artifact exceeds size limit")
        document = json.loads(path.read_text())
        if document.get("schema") not in (SCHEMA, IMPLICIT_SCHEMA):
            raise ArtifactError("unsupported schema")
        if (
            hashlib.sha256(_canonical(document["payload"])).hexdigest()
            != document["sha256"]
        ):
            raise ArtifactError("artifact hash mismatch")
        result = Codec().decode(document["payload"])
        if document.get("schema") == IMPLICIT_SCHEMA and not isinstance(
            result, ImplicitDAEReductionResult
        ):
            raise ArtifactError("implicit schema requires an implicit result")
        if isinstance(result, ImplicitDAEReductionResult):
            if document.get("schema") != IMPLICIT_SCHEMA:
                raise ArtifactError("implicit result requires its own schema")
            from equireduce.implicit_artifacts import replay_implicit_result

            result = replay_implicit_result(result)
            check = result.symbolic_check
        else:
            check = None
        if not isinstance(
            result, (ReductionResult, DAEReductionResult, ImplicitDAEReductionResult)
        ):
            raise ArtifactError("expected a reduction result")
        if isinstance(result, ImplicitDAEReductionResult):
            check = result.symbolic_check
        elif isinstance(result, DAEReductionResult):
            check = verify_dae_certificate(result.source, result.certificate)
        else:
            check = verify_certificate(result.source, result.certificate)
        expected_hash = hashlib.sha256(
            _canonical(Codec().encode(result.certificate))
        ).hexdigest()
        if expected_hash != document["mathematical_sha256"]:
            raise ArtifactError("mathematical content hash mismatch")
        if check.status.value != "verified":
            raise ArtifactError("artifact certificate did not verify")
        compared_fields: tuple[str, ...] = (
            "source",
            "reduced_system",
            "remaining_unknowns",
            "reconstruction",
            "conditions",
            "additional_conditions",
            "coverage",
            "assumption_consistency",
            "coordinate_map",
            "metrics",
        )
        expected: ReductionResult | DAEReductionResult | ImplicitDAEReductionResult
        if isinstance(result, ImplicitDAEReductionResult):
            compared_fields = ()
            expected = result
        elif isinstance(result, DAEReductionResult):
            expected = _from_dae_certificate(
                result.certificate,
                initial_time=result.initial_check.time,
                initial_values=dict(result.initial_check.values)
                if result.initial_check.time is not None
                else None,
            )
            compared_fields = tuple(
                f.name
                for f in fields(result)
                if f.name not in ("symbolic_check", "formal_check")
            )
        else:
            expected = (
                _from_coordinate_certificate(result.certificate)
                if isinstance(result.certificate, CoordinateCertificate)
                else _from_core(result.source, result.certificate.reduction)
            )
        for field in compared_fields:
            if field == "metrics" and getattr(result, "metrics", None) is None:
                continue
            if getattr(result, field) != getattr(expected, field):
                raise ArtifactError(
                    f"artifact {field}/coverage does not match certificate"
                )
        formal = result.formal_check
        if formal.source is not None:
            from equireduce.lean import generate_lean

            if formal.source != generate_lean(result.source, result.certificate):
                raise ArtifactError("stored proof does not match certificate")
            if (
                hashlib.sha256(formal.source.encode()).hexdigest()
                != formal.source_sha256
            ):
                raise ArtifactError("stored proof hash mismatch")
        return replace(
            result,
            symbolic_check=check,
            formal_check=replace(formal, origin="recorded"),
        )
    except ArtifactError:
        raise
    except (
        OSError,
        ValueError,
        TypeError,
        KeyError,
        AttributeError,
        RecursionError,
        CertificateError,
    ) as exc:
        raise ArtifactError(f"invalid artifact: {exc}") from exc
