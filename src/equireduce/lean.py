"""Real Lean compilation with explicit failure states and axiom auditing."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
import tempfile
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

import sympy as sp

from equireduce._lean_export import LeanExportError, generate_lean_reduction_source
from equireduce.api import verify_certificate
from equireduce.dae import DAECertificate, DAESystem, verify_dae_certificate
from equireduce.errors import (
    CertificateError,
    ProofVerificationError,
    UnsupportedExpressionError,
)
from equireduce.implicit import ImplicitDAESystem
from equireduce.implicit_reduction import (
    ImplicitReductionCertificate,
    verify_implicit_certificate,
)
from equireduce.result import (
    Certificate,
    CoordinateCertificate,
    FormalCheck,
    LeanConfig,
    ProofStatus,
)
from equireduce.system import System
from equireduce.time_coordinates import (
    ImplicitCoordinateCertificate,
    verify_implicit_coordinate_certificate,
)

MATHLIB_REVISION = "fc4f59e577feb1a4956671bc04ac18aaaf8cd842"
TOOLCHAIN = "leanprover/lean4:v4.36.0"
ALLOWED_AXIOMS = {"propext", "Classical.choice", "Quot.sound"}


def generate_lean(
    system: System | DAESystem | ImplicitDAESystem,
    certificate: Certificate
    | CoordinateCertificate
    | DAECertificate
    | ImplicitReductionCertificate
    | ImplicitCoordinateCertificate,
    *,
    config: LeanConfig | None = None,
) -> str:
    """Export the exact caller-supplied system and checked trace."""
    if isinstance(certificate, ImplicitCoordinateCertificate):
        from equireduce._time_coordinate_lean import generate_time_coordinate_lean

        check = verify_implicit_coordinate_certificate(system, certificate)
        if check.status.value != "verified":
            raise CertificateError("; ".join((*check.failures, *check.unresolved)))
        return generate_time_coordinate_lean(certificate)
    if isinstance(certificate, ImplicitReductionCertificate):
        check = verify_implicit_certificate(system, certificate)
        if check.status.value != "verified":
            raise CertificateError("; ".join((*check.failures, *check.unresolved)))
        from equireduce._implicit_lean import generate_implicit_lean

        return generate_implicit_lean(certificate)
    if isinstance(certificate, DAECertificate):
        from equireduce._dae_lean import generate_dae_lean

        check = verify_dae_certificate(system, certificate)
        if check.status.value != "verified":
            raise CertificateError("; ".join((*check.failures, *check.unresolved)))
        return generate_dae_lean(certificate)
    if not isinstance(system, System):
        raise CertificateError("algebraic certificate requires an algebraic System")
    check = verify_certificate(system, certificate)
    if check.status.value != "verified":
        raise CertificateError("; ".join((*check.failures, *check.unresolved)))
    if isinstance(certificate, CoordinateCertificate):
        from equireduce._coordinate_lean import generate_coordinate_lean

        return generate_coordinate_lean(certificate)
    core = certificate.reduction
    expressions = (*core.source_residuals, *core.reduced_residuals, *core.conditions)
    for expression in expressions:
        for node in sp.preorder_traversal(expression):
            if (
                isinstance(node, sp.Function)
                and node.func is not sp.exp
                and not isinstance(node, sp.core.function.AppliedUndef)
            ):
                raise UnsupportedExpressionError(
                    f"Lean export does not yet support {node.func}"
                )
            if isinstance(node, sp.Pow) and node.exp.is_integer is not True:
                raise UnsupportedExpressionError(
                    "Lean export currently requires integer powers"
                )
    try:
        source = generate_lean_reduction_source(core)
        if any(v.has(sp.exp) for v in expressions):
            source = "import Mathlib.Analysis.SpecialFunctions.ExpDeriv\n" + source
        return source
    except LeanExportError as exc:
        raise UnsupportedExpressionError(str(exc)) from exc


def compile_source(source: str, *, config: LeanConfig | None) -> FormalCheck:
    """Compile a theorem; this function alone does not associate it with an input."""
    digest = hashlib.sha256(source.encode()).hexdigest()
    started = perf_counter()
    command = ()

    def outcome(status, output, **kwargs):
        return FormalCheck(
            status,
            source=source,
            output=output,
            source_sha256=digest,
            command=command,
            seconds=perf_counter() - started,
            checked_at_utc=datetime.now(UTC).isoformat(),
            **kwargs,
        )

    if re.search(r"\b(sorry|admit|axiom|unsafe)\b", source):
        return outcome(ProofStatus.FAILED, "forbidden proof placeholder or declaration")
    if config is None or shutil.which(config.command[0]) is None:
        return outcome(
            ProofStatus.UNAVAILABLE, "Lean executable/configuration is unavailable"
        )
    directory = Path(config.project_dir).resolve()
    try:
        manifest = json.loads((directory / "lake-manifest.json").read_text())
        toolchain = (directory / "lean-toolchain").read_text().strip()
        revision = next(
            p["rev"] for p in manifest["packages"] if p["name"] == "mathlib"
        )
    except (OSError, ValueError, KeyError, StopIteration) as exc:
        return outcome(ProofStatus.UNAVAILABLE, f"unprepared Lean project: {exc}")
    if toolchain != TOOLCHAIN or revision != MATHLIB_REVISION:
        return outcome(ProofStatus.UNSUPPORTED, "unrecognized Lean/Mathlib versions")
    try:
        for package in manifest["packages"]:
            package_dir = directory / ".lake/packages" / package["name"]
            head = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
            changed = subprocess.run(
                ["git", "status", "--porcelain", "--untracked-files=no"],
                cwd=package_dir,
                capture_output=True,
                text=True,
                timeout=10,
                check=True,
            ).stdout.strip()
            if head != package["rev"] or changed:
                return outcome(
                    ProofStatus.FAILED,
                    f"dependency revision/content mismatch: {package['name']}",
                )
        version = subprocess.run(
            [*config.command, "--version"],
            cwd=directory,
            capture_output=True,
            text=True,
            timeout=config.timeout_seconds,
        )
        if version.returncode or "version 4.36.0," not in version.stdout:
            return outcome(ProofStatus.UNAVAILABLE, version.stdout + version.stderr)
        with tempfile.TemporaryDirectory(
            prefix="equireduce_", dir=directory / ".lake"
        ) as temp:
            proof = Path(temp) / "Proof.lean"
            proof.write_text(source, encoding="utf-8")
            command = (*config.command, "-DwarningAsError=true", str(proof))
            compiled = subprocess.run(
                command,
                cwd=directory,
                capture_output=True,
                text=True,
                timeout=config.timeout_seconds,
            )
    except subprocess.TimeoutExpired as exc:
        return outcome(ProofStatus.TIMEOUT, str(exc))
    except (OSError, subprocess.CalledProcessError) as exc:
        return outcome(ProofStatus.UNAVAILABLE, str(exc))
    output = compiled.stdout + compiled.stderr
    match = re.search(
        r"'reduction_equivalence' depends on axioms:\s*\[([^]]*)\]", output
    )
    no_axioms = "'reduction_equivalence' does not depend on any axioms" in output
    axioms = (
        tuple(value.strip() for value in match[1].split(",") if value.strip())
        if match
        else ()
    )
    success = (
        compiled.returncode == 0
        and (match or no_axioms)
        and set(axioms) <= ALLOWED_AXIOMS
    )
    return outcome(
        ProofStatus.VERIFIED if success else ProofStatus.FAILED,
        output,
        returncode=compiled.returncode,
        axioms=axioms,
        toolchain_version=version.stdout.strip(),
        mathlib_revision=revision,
        origin="compiled",
    )


def verify_with_lean(
    system: System | DAESystem | ImplicitDAESystem,
    certificate: Certificate
    | CoordinateCertificate
    | DAECertificate
    | ImplicitReductionCertificate
    | ImplicitCoordinateCertificate,
    *,
    config: LeanConfig | None,
) -> FormalCheck:
    """Verify the certificate and compile its exact formal translation."""
    try:
        source = generate_lean(system, certificate)
    except CertificateError as exc:
        return FormalCheck(ProofStatus.FAILED, output=str(exc))
    except UnsupportedExpressionError as exc:
        return FormalCheck(ProofStatus.UNSUPPORTED, output=str(exc))
    return compile_source(source, config=config)


def attach_proof(result, *, proof, config):
    if proof == "generate":
        try:
            source = generate_lean(result.source, result.certificate)
            check = FormalCheck(
                ProofStatus.GENERATED,
                source=source,
                source_sha256=hashlib.sha256(source.encode()).hexdigest(),
            )
        except UnsupportedExpressionError as exc:
            check = FormalCheck(ProofStatus.UNSUPPORTED, output=str(exc))
    else:
        check = verify_with_lean(result.source, result.certificate, config=config)
    if proof == "require" and check.status is not ProofStatus.VERIFIED:
        raise ProofVerificationError(
            f"required Lean proof: {check.status.value}\n{check.output}",
            candidate=result,
            verification=check,
        )
    return replace(result, formal_check=check)
