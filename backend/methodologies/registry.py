"""Registry of analysis methodologies.

The registry is the only place that knows which methodologies exist. It is
deliberately trivial: methodologies register themselves by being imported, so
adding a new one never modifies this file or any other methodology.

Auto-discovery: :func:`discover` imports every subpackage of
``backend.methodologies`` and collects its ``METHODOLOGY`` singleton when the
package defines one. A package without one (e.g. ``base``) is skipped.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil

from backend.methodologies.base import Methodology

logger = logging.getLogger("backend.methodologies.registry")


class MethodologyRegistry:
    """Holds the registered methodologies and answers lookup questions."""

    def __init__(self) -> None:
        self._items: dict[str, Methodology] = {}

    # ------------------------------------------------------------------
    def register(self, methodology: Methodology) -> None:
        """Add a methodology. Re-registering a name replaces it (tests)."""
        key = methodology.name
        if key in self._items:
            logger.debug("replacing registered methodology %r", key)
        self._items[key] = methodology

    def get(self, name: str) -> Methodology | None:
        """Look up by name, or None."""
        return self._items.get(name)

    def list(self) -> list[str]:
        """Registered names, sorted so output is deterministic."""
        return sorted(self._items)

    def all(self) -> list[Methodology]:
        """Registered methodologies, sorted by name."""
        return [self._items[name] for name in self.list()]

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, name: str) -> bool:
        return name in self._items


# The single process-level registry.
registry = MethodologyRegistry()


def discover() -> int:
    """Import every methodology subpackage and register its singleton.

    Returns the number of methodologies now registered. Idempotent: calling it
    twice does not duplicate entries (the registry replaces by name).
    """
    package = importlib.import_module("backend.methodologies")
    before = len(registry)
    for module_info in pkgutil.iter_modules(package.__path__):
        if module_info.name.startswith("_") or module_info.name == "base":
            continue
        try:
            module = importlib.import_module(
                f"backend.methodologies.{module_info.name}"
            )
        except Exception as exc:  # noqa: BLE001 — one bad package must not hide the rest
            logger.warning(
                "methodologies: could not import %s: %s", module_info.name, exc
            )
            continue
        singleton = getattr(module, "METHODOLOGY", None)
        if isinstance(singleton, Methodology):
            registry.register(singleton)
            logger.debug("registered methodology %r", singleton.name)
    return len(registry) - before
