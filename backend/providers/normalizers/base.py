"""Normalizer contract: converts provider raw data into the canonical format."""

from __future__ import annotations

from abc import ABC, abstractmethod

from backend.domain.value_objects.financials_normalized import (
    NormalizedFinancials,
    ProviderName,
    RawFinancialsYear,
)


class FinancialNormalizer(ABC):
    """Converts a provider-specific raw year bundle into normalized data.

    Normalizers are the ONLY place where provider-specific quirks (label
    aliases, sign conventions, fallback derivations) are translated into the
    canonical :class:`NormalizedFinancials` shape. Providers never produce
    normalized data and analytics never sees raw data.
    """

    @property
    @abstractmethod
    def source(self) -> ProviderName:
        """Provider name this normalizer understands."""

    @abstractmethod
    def normalize(self, raw: RawFinancialsYear) -> NormalizedFinancials | None:
        """Build the normalized record for one fiscal year.

        Returns None when the raw year contains no usable data.
        """
