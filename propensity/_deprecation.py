"""Announcing a stable name's removal. Internal: the policy is docs/stability.md.

A name is deprecated for at least one minor release before it goes. During that time it keeps
working and warns, so that upgrading is never a surprise.
"""

import warnings

from .errors import PropensityDeprecationWarning


def warn_deprecated(what: str, *, instead: str | None = None, removed_in: str | None = None,
                    stacklevel: int = 3) -> None:
    """Warns that `what` is deprecated, naming its replacement and when it goes.

    stacklevel 3 points at the caller of the deprecated function, not at the function itself.
    """
    message = f"{what} is deprecated"
    if removed_in:
        message += f" and will be removed in {removed_in}"
    if instead:
        message += f"; use {instead} instead"
    warnings.warn(message, PropensityDeprecationWarning, stacklevel=stacklevel)
