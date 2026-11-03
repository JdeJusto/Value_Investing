"""Read the precomputed peer-stats artifact for the scorecard (Phase 5).

The artifact (``data/peer_stats/<level>_<slug>.json``) is built weekly by
``scripts/build_peer_stats.py`` and is **read-only** here: the scorecard never
computes a peer distribution itself, it only asks where one value sits inside
the distribution the artifact stored.

See ``docs/scorecard_design.md`` §5. The service is deliberately rule-agnostic:
:class:`~backend.services.scorecard_service.ScorecardService` knows which rule
compares against which metric.

Degradation is total: a missing file, malformed JSON, a group below the
minimum size or a metric with no stored values simply yields ``None``, and the
caller leaves the rule untouched. Nothing here raises.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import pairwise
from pathlib import Path
from typing import Any

from backend.analytics.peer_stats import MIN_GROUP_COMPANIES, percentile_rank, slugify

#: Where ``scripts/build_peer_stats.py`` writes the artifact (git-ignored).
DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "peer_stats"

#: Quantiles stored per metric, fine-to-coarse, used for the fallback
#: interpolation when the artifact has no ``values`` array.
_QUANTILE_POINTS: tuple[tuple[float, str], ...] = (
    (0.0, "min"),
    (0.10, "p10"),
    (0.25, "p25"),
    (0.50, "median"),
    (0.75, "p75"),
    (0.90, "p90"),
    (1.0, "max"),
)


@dataclass(frozen=True)
class PeerGroup:
    """The resolved peer group for one company."""

    level: str  # "industry" | "sector"
    name: str
    size: int
    artifact: dict[str, Any]


class PeerStatsService:
    """Read-only access to the peer-stats artifact (parsed once per group)."""

    def __init__(self, base_dir: str | Path | None = None) -> None:
        self._base = Path(base_dir) if base_dir is not None else DEFAULT_DIR
        self._cache: dict[str, dict[str, Any] | None] = {}

    # -- loading ----------------------------------------------------------
    def for_group(self, level: str, group: str) -> dict[str, Any] | None:
        """The artifact for one ``(level, group)``, or ``None``."""
        name = str(group or "").strip()
        if not name:
            return None
        key = f"{level}_{slugify(name)}"
        if key in self._cache:
            return self._cache[key]
        data: dict[str, Any] | None = None
        try:
            loaded = json.loads(
                (self._base / f"{key}.json").read_text(encoding="utf-8")
            )
        except (OSError, ValueError):
            loaded = None
        if isinstance(loaded, dict) and isinstance(loaded.get("metrics"), dict):
            data = loaded
        self._cache[key] = data
        return data

    def group_for(
        self, *, sector: str | None, industry: str | None
    ) -> PeerGroup | None:
        """Resolve a company's peer group: industry first, then sector.

        A group whose ``company_count`` is below
        :data:`~backend.analytics.peer_stats.MIN_GROUP_COMPANIES` is treated as
        unavailable (the generator would not have written it, but a stale or
        hand-edited artifact must not slip through).
        """
        for level, name in (("industry", industry), ("sector", sector)):
            data = self.for_group(level, name or "")
            if data is None:
                continue
            try:
                size = int(data.get("company_count") or 0)
            except (TypeError, ValueError):
                size = 0
            if size < MIN_GROUP_COMPANIES:
                continue
            return PeerGroup(
                level=level, name=str(name).strip(), size=size, artifact=data
            )
        return None

    # -- queries ----------------------------------------------------------
    def metric(self, level: str, group: str, metric: str) -> dict[str, Any] | None:
        """One metric's stored summary (``n``, quantiles, ``values``)."""
        data = self.for_group(level, group)
        if data is None:
            return None
        entry = (data.get("metrics") or {}).get(metric)
        return entry if isinstance(entry, dict) else None

    def median(self, level: str, group: str, metric: str) -> float | None:
        """The metric's peer median, or ``None``."""
        entry = self.metric(level, group, metric)
        if entry is None:
            return None
        value = entry.get("median", entry.get("p50"))
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return float(value)
        return None

    def percentile(
        self, level: str, group: str, metric: str, value: float | None
    ) -> float | None:
        """Where ``value`` sits in the peer distribution, in ``[0, 1]``.

        Exact rank over the stored sorted ``values`` (share strictly below,
        ties ½), so a company at the median reads ≈ 0.5. Falls back to linear
        interpolation between the stored quantiles if a (hand-built) artifact
        has no ``values`` array.
        """
        if value is None:
            return None
        entry = self.metric(level, group, metric)
        if entry is None:
            return None
        values = entry.get("values")
        if isinstance(values, list) and values:
            return percentile_rank(values, float(value))
        return self._percentile_from_quantiles(entry, float(value))

    def _percentile_from_quantiles(
        self, entry: dict[str, Any], value: float
    ) -> float | None:
        """Interpolate a percentile from stored quantiles (no ``values``)."""
        points: list[tuple[float, float]] = []
        for probability, key in _QUANTILE_POINTS:
            raw = entry.get(key)
            if isinstance(raw, (int, float)):
                points.append((float(probability), float(raw)))
        if len(points) < 2:
            return None
        if value < points[0][1]:
            return 0.0
        if value > points[-1][1]:
            return 1.0
        for (q0, v0), (q1, v1) in pairwise(points):
            if value <= v1:
                if v1 == v0:
                    return q1
                return q0 + (q1 - q0) * ((value - v0) / (v1 - v0))
        return 1.0

    def clear_cache(self) -> None:
        """Drop the parsed artifacts (tests and long-lived processes)."""
        self._cache.clear()
