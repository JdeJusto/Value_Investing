"""Base classes for the multi-methodology analysis engine.

Each investment methodology (Graham, Fisher, Buffett/Clark, Graham & Dodd) is
a self-contained package under ``backend/methodologies/`` that produces its
own verdict, metrics and reasoning. Methodologies never read each other's
output, so two of them can disagree without either being "wrong".

The rules this module exists to guarantee (see
``docs/methodology_decisions.md``):

- a methodology is an independent column, never a contributor to a composite
  score;
- ``score`` is optional — a PASS/FAIL-only methodology returns ``None``;
- every claim carries a :class:`SourceRef` with book, edition, page, era and a
  US-specific caution, because the sources are historical;
- adding a methodology never modifies an existing one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Verdict(str, Enum):
    """The verdict a methodology returns for one company."""

    BUY = "BUY"
    WATCH = "WATCH"
    HOLD = "HOLD"
    AVOID = "AVOID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


class Confidence(str, Enum):
    """How much the methodology trusts its own verdict."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


@dataclass(frozen=True)
class SourceRef:
    """Provenance of one rule or metric.

    ``era`` and ``us_caution`` are mandatory because every book in the canon is
    historical: the thresholds were written for a specific market and time, and
    the system must not present them as timeless.
    """

    book: str
    edition: str
    year: int
    page: str
    era: str
    us_caution: str | None = None


@dataclass(frozen=True)
class Rule:
    """One explicit rule of a methodology."""

    id: str
    name: str
    description: str
    kind: str  # "EXPLICIT" | "INFERRED" | "EXCEPTION"
    source: SourceRef


@dataclass
class MethodologyResult:
    """The output of one methodology for one company.

    ``score`` is ``None`` when the methodology has no numeric scale (Decision
    10). Consumers must render that as an em-dash, never as ``0.0``.
    """

    methodology: str
    version: str
    family: str
    verdict: Verdict
    score: float | None
    metrics: dict[str, Any]
    reasons: list[str]
    red_flags: list[str]
    confidence: Confidence
    sources: list[SourceRef]
    failed_rules: list[str] = field(default_factory=list)
    passed_rules: list[str] = field(default_factory=list)


class Methodology(ABC):
    """One investment philosophy, self-contained.

    Implementations receive already-fetched fundamentals and prices; they
    never touch the network or the database themselves, which keeps them
    deterministic and testable.
    """

    name: str
    version: str
    family: str

    @abstractmethod
    def evaluate(
        self,
        ticker: str,
        fundamentals: Any,
        prices: Any,
    ) -> MethodologyResult:
        """Evaluate one company and return the methodology's own verdict."""

    @abstractmethod
    def rules(self) -> list[Rule]:
        """The explicit rules this methodology applies, for display."""

    @abstractmethod
    def metadata(self) -> dict:
        """Book, edition, pages, known limitations, family."""
