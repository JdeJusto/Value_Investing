class ValueInvestingError(Exception):
    """Base exception for the application."""


class ProviderError(ValueInvestingError):
    """Error from a data provider."""


class EdgarError(ProviderError):
    """Error from EDGAR/SEC provider."""


class YahooFinanceError(ProviderError):
    """Error from Yahoo Finance provider."""


class RateLimitError(ProviderError):
    """Rate limit exceeded on a provider."""


class DownloadError(ProviderError):
    """Failed to download data from a provider."""


class ParserError(ValueInvestingError):
    """Error parsing data."""


class XBRLError(ParserError):
    """Error parsing XBRL data."""


class ValidationError(ValueInvestingError):
    """Data validation error."""


class ConfigurationError(ValueInvestingError):
    """Missing or invalid configuration."""


class CacheError(ValueInvestingError):
    """Cache operation error."""
