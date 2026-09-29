from abc import ABC, abstractmethod
from typing import Optional


class Repository(ABC):
    @abstractmethod
    def get(self, key: str) -> dict | None: ...

    @abstractmethod
    def set(self, key: str, value: dict) -> None: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
