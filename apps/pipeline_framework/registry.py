"""Stage type registration and third-party entry-point discovery."""

from __future__ import annotations

from dataclasses import dataclass
from importlib import metadata
from typing import Any, Callable

from pydantic import BaseModel


StageFactory = Callable[[BaseModel], Any]


@dataclass(frozen=True)
class StageDefinition:
    type_name: str
    factory: StageFactory
    config_model: type[BaseModel]
    accepts: type[Any] | None
    emits: type[Any] | None
    source: bool = False


class StageRegistry:
    """Maps manifest stage type names to validated factories and contracts."""

    def __init__(self) -> None:
        self._definitions: dict[str, StageDefinition] = {}

    def register(
        self,
        type_name: str,
        factory: StageFactory,
        config_model: type[BaseModel],
        *,
        accepts: type[Any] | None,
        emits: type[Any] | None,
        source: bool = False,
    ) -> None:
        if not type_name:
            raise ValueError("type_name is required")
        if type_name in self._definitions:
            raise ValueError(f"stage type '{type_name}' is already registered")
        if source and accepts is not None:
            raise ValueError("source stages cannot accept payloads")
        self._definitions[type_name] = StageDefinition(
            type_name=type_name,
            factory=factory,
            config_model=config_model,
            accepts=accepts,
            emits=emits,
            source=source,
        )

    def get(self, type_name: str) -> StageDefinition | None:
        return self._definitions.get(type_name)

    def require(self, type_name: str) -> StageDefinition:
        definition = self.get(type_name)
        if definition is None:
            raise KeyError(f"unknown stage type '{type_name}'")
        return definition

    def validate_config(self, type_name: str, values: dict[str, Any]) -> BaseModel:
        return self.require(type_name).config_model.model_validate(values)

    def create(self, type_name: str, config: BaseModel) -> Any:
        return self.require(type_name).factory(config)

    def discover(self, group: str = "tiger.stages") -> None:
        for entry_point in metadata.entry_points(group=group):
            register = entry_point.load()
            register(self)