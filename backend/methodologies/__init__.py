"""Multi-methodology analysis engine.

Each methodology is an independent package under ``backend/methodologies/``;
this package only holds the shared base classes and the registry. See
``docs/methodology_decisions.md`` for the design decisions that constrain
both.
"""

from __future__ import annotations

from backend.methodologies.base import (
    Confidence,
    Methodology,
    MethodologyResult,
    Rule,
    SourceRef,
    Verdict,
)
from backend.methodologies.registry import MethodologyRegistry, discover, registry

__all__ = [
    "Confidence",
    "Methodology",
    "MethodologyRegistry",
    "MethodologyResult",
    "Rule",
    "SourceRef",
    "Verdict",
    "discover",
    "registry",
]
