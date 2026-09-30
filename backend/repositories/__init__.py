"""Repository package.

The concrete repositories are exposed here but imported *lazily* via module
``__getattr__`` (PEP 562): ``SqlAlchemyFinancialRepository`` pulls in SQLAlchemy
(~0.4 s of import time), so eagerly importing it at package load made every
``import backend.repositories.<anything>`` slow even for the FDB/JSON adapters.
Attribute access keeps working exactly as before.
"""

__all__ = [
    "FinancialDatabaseRepository",
    "JsonFinancialRepository",
    "SqlAlchemyFinancialRepository",
]


def __getattr__(name):
    if name == "SqlAlchemyFinancialRepository":
        from backend.repositories.financial_repository import (
            SqlAlchemyFinancialRepository as _cls,
        )
    elif name == "JsonFinancialRepository":
        from backend.repositories.json_financial_repository import (
            JsonFinancialRepository as _cls,
        )
    elif name == "FinancialDatabaseRepository":
        from backend.repositories.financial_database_repository import (
            FinancialDatabaseRepository as _cls,
        )
    else:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    globals()[name] = _cls
    return _cls
