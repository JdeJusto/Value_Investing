from abc import ABC, abstractmethod
from typing import Any, Optional


class CacheProvider(ABC):
    @abstractmethod
    def get(self, key: str) -> Any | None: ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl: int = 300) -> None: ...

    @abstractmethod
    def clear(self) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
