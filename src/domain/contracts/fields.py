from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ConfigFieldSpec:
    key: str
    default: Any
    value_type: type
    allowed: tuple[Any, ...] | None = None
    min_value: float | None = None
    max_value: float | None = None
    label_key: str | None = None
    ui_group: str | None = None
    visible_when: str | None = None

    def validate_allowed(self, value: Any, *, path: str) -> None:
        if self.allowed is not None and value not in self.allowed:
            allowed_values = ", ".join(str(item) for item in self.allowed)
            raise ValueError(f"{path} must be one of: {allowed_values}")

    def validate_range(self, value: float, *, path: str) -> None:
        if self.min_value is not None and value < self.min_value:
            raise ValueError(_range_message(path, self.min_value, self.max_value))
        if self.max_value is not None and value > self.max_value:
            raise ValueError(_range_message(path, self.min_value, self.max_value))


def _range_message(path: str, min_value: float | None, max_value: float | None) -> str:
    if min_value is not None and max_value is not None:
        return f"{path} must be between {_format_number(min_value)} and {_format_number(max_value)}"
    if min_value is not None:
        return f"{path} must be greater than or equal to {_format_number(min_value)}"
    if max_value is not None:
        return f"{path} must be less than or equal to {_format_number(max_value)}"
    return f"{path} is out of range"


def _format_number(value: float) -> str:
    if float(value).is_integer():
        return str(int(value))
    return str(value)
