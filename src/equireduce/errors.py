"""Public errors for equation validation, certification, and proof execution."""


class EquiReduceError(Exception):
    """Base library error."""


class InvalidSystemError(EquiReduceError, ValueError):
    """The input does not satisfy the system contract."""


class UnsupportedDomainError(InvalidSystemError):
    """The requested mathematical domain is not implemented."""


class UnsupportedExpressionError(InvalidSystemError):
    """An expression has no supported semantics."""


class CertificateError(EquiReduceError, ValueError):
    """An algebraic certificate did not verify."""


class ProofVerificationError(EquiReduceError):
    """A required formal proof was not verified."""

    def __init__(self, message, *, candidate=None, verification=None):
        super().__init__(message)
        self.candidate = candidate
        self.verification = verification


class ArtifactError(EquiReduceError, ValueError):
    """An artifact cannot be decoded or validated."""
