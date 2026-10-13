"""Validation helpers for filesystem paths built from caller-supplied values.

Several services build a file path from a value the caller controls — a
ticker, a date, an accession number. Without validation a value such as
``../../etc/passwd`` would escape the intended directory (CWE-22, and the
``py/path-injection`` query). Every such value must go through
:func:`safe_component` (a single identifier segment) or :func:`safe_join`
(segment(s) joined under a fixed base directory).

:func:`safe_join` is also the sanitiser static analysis recognises: it
normalises the joined path with :func:`os.path.realpath` and verifies that
the result stays inside the base directory, then returns the normalised
path so callers use the value that was actually checked.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

#: Characters allowed in any single component. The same class is used for a
#: terse identifier (a ticker) and for a file name; only the length cap differs.
_SAFE_CHARS = re.compile(r"^[A-Za-z0-9._-]+$")

#: A ticker (and similar identifiers) is at most 20 characters: every
#: NASDAQ/NYSE symbol is 5 or fewer plus class suffixes such as ``BRK.B``.
MAX_IDENTIFIER_LENGTH = 20
#: A file-name component can be longer (``consensus_2024-12-31.json``).
MAX_FILENAME_LENGTH = 255


class UnsafePathComponent(ValueError):
    """Raised when a caller-supplied string is not a safe path segment."""


def _validate(value: str, max_length: int) -> str:
    """Return ``value`` stripped, or raise :class:`UnsafePathComponent`."""
    if not isinstance(value, str):
        raise UnsafePathComponent(f"expected str, got {type(value).__name__}")
    component = value.strip()
    if not component:
        raise UnsafePathComponent("empty path component")
    if component in {".", ".."}:
        raise UnsafePathComponent(f"dot/dotdot path component: {value!r}")
    if "/" in component or "\\" in component:
        raise UnsafePathComponent(f"separator in path component: {value!r}")
    if len(component) > max_length:
        raise UnsafePathComponent(
            f"path component too long ({len(component)} > {max_length}): {value!r}"
        )
    if not _SAFE_CHARS.match(component):
        raise UnsafePathComponent(f"unsafe characters in path component: {value!r}")
    return component


def safe_component(value: str) -> str:
    """Validate a single identifier (a ticker) and return it unchanged.

    Raises :class:`UnsafePathComponent` for anything that is not a plain
    ``[A-Za-z0-9._-]`` token of at most :data:`MAX_IDENTIFIER_LENGTH`
    characters. ``.`` and ``..`` and any value containing a path separator
    are rejected, so the result can never escape the directory it is joined
    to.
    """
    return _validate(value, MAX_IDENTIFIER_LENGTH)


def safe_join(base: Path, *components: str) -> Path:
    """Join ``base`` with validated ``components`` and confine the result.

    Each component is validated as a file-name segment, then the joined path
    is normalised with :func:`os.path.realpath` and checked to remain inside
    ``base``; a component that would escape raises
    :class:`UnsafePathComponent`. The normalised path is returned.
    """
    base_path = Path(base)
    base_real = os.path.realpath(str(base_path))
    parts = [_validate(component, MAX_FILENAME_LENGTH) for component in components]
    candidate = os.path.join(base_real, *parts)
    final = os.path.realpath(candidate)
    # The ``os.sep`` suffix avoids the ``/data`` vs ``/data-evil`` prefix trap.
    if final != base_real and not final.startswith(base_real + os.sep):
        raise UnsafePathComponent(f"path {final!r} escapes base {base_real!r}")
    return Path(final)
