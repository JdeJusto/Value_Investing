from abc import ABC, abstractmethod
from typing import Any


class MetricCalculator(ABC):
    @abstractmethod
    def calculate(self, **kwargs) -> Any: ...
