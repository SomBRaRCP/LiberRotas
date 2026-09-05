"""Typed failures used across trust boundaries."""


class TRQBECError(Exception):
    """Base class for controlled TRQ-BEC failures."""


class ContractError(TRQBECError):
    """A canonical contract is malformed or ambiguous."""


class CryptoError(TRQBECError):
    """A cryptographic operation failed closed."""


class PolicyError(TRQBECError):
    """A policy is invalid or unsupported."""


class LedgerError(TRQBECError):
    """Evidence could not be recorded or verified safely."""

