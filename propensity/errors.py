"""Exceptions and warnings raised by the pipeline."""


class PropensityError(Exception):
    """Base class for every error this package raises on purpose."""


class ParseError(PropensityError):
    """An annotator response did not contain a usable demand interval."""


class ProviderError(PropensityError):
    """A provider is misconfigured or cannot do what was asked of it."""


class ContractError(PropensityError, ValueError):
    """Input data violates a data contract (CLAUDE.md §6).

    `rows` holds the offending rows (or column names) so callers can report them.
    """

    def __init__(self, message: str, rows: list | None = None):
        super().__init__(message)
        self.rows = rows or []


class DataWarning(UserWarning):
    """Data that can be used but probably should not be trusted without a look."""
