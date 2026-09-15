"""Shared structural types for canonical JSON payloads."""

from __future__ import annotations

from typing import TypeAlias

JsonValue: TypeAlias = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]

__all__ = ["JsonValue"]
