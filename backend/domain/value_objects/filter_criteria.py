from dataclasses import dataclass
from enum import Enum
from typing import Any


class FilterOperator(Enum):
    EQ = "eq"
    NEQ = "neq"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    BETWEEN = "between"
    IS_NONE = "is_none"
    IS_NOT_NONE = "is_not_none"


@dataclass
class FilterCriteria:
    field: str
    operator: FilterOperator
    value: Any | None = None

    def matches(self, metric_value: Any) -> bool:
        if metric_value is None:
            return self.operator == FilterOperator.IS_NONE

        if self.operator == FilterOperator.IS_NONE:
            return metric_value is None
        if self.operator == FilterOperator.IS_NOT_NONE:
            return metric_value is not None

        if self.value is None:
            return True

        try:
            left = float(metric_value)
        except (TypeError, ValueError):
            return False

        if self.operator == FilterOperator.EQ:
            try:
                return left == float(self.value)
            except (TypeError, ValueError):
                return str(metric_value) == str(self.value)

        if self.operator == FilterOperator.NEQ:
            try:
                return left != float(self.value)
            except (TypeError, ValueError):
                return str(metric_value) != str(self.value)

        if self.operator in (
            FilterOperator.GT,
            FilterOperator.GTE,
            FilterOperator.LT,
            FilterOperator.LTE,
        ):
            try:
                right = float(self.value)
            except (TypeError, ValueError):
                return False
            if self.operator == FilterOperator.GT:
                return left > right
            if self.operator == FilterOperator.GTE:
                return left >= right
            if self.operator == FilterOperator.LT:
                return left < right
            return left <= right

        if self.operator == FilterOperator.BETWEEN:
            if not isinstance(self.value, (list, tuple)) or len(self.value) != 2:
                return False
            try:
                low, high = float(self.value[0]), float(self.value[1])
                return low <= left <= high
            except (TypeError, ValueError):
                return False

        return False

    @classmethod
    def lt(cls, field: str, value: float) -> FilterCriteria:
        return cls(field=field, operator=FilterOperator.LT, value=value)

    @classmethod
    def gt(cls, field: str, value: float) -> FilterCriteria:
        return cls(field=field, operator=FilterOperator.GT, value=value)

    @classmethod
    def between(cls, field: str, low: float, high: float) -> FilterCriteria:
        return cls(field=field, operator=FilterOperator.BETWEEN, value=(low, high))

    @classmethod
    def eq(cls, field: str, value: Any) -> FilterCriteria:
        return cls(field=field, operator=FilterOperator.EQ, value=value)
