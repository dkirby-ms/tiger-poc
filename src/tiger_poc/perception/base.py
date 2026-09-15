"""Transport-neutral interface implemented by perception workloads."""

from __future__ import annotations

from typing import Protocol, TypeVar, runtime_checkable

from tiger_poc.perception.observation import Observation

FrameT = TypeVar("FrameT", contravariant=True)


@runtime_checkable
class PerceptionWorkload(Protocol[FrameT]):
    """Consume frames and emit observations without coupling to a camera runtime."""

    @property
    def runtime(self) -> str:
        """Return the inference runtime identifier recorded on observations."""
        ...

    def observe(self, frame: FrameT) -> list[Observation]:
        """Return zero or more observations for one frame."""
        ...

    def reset(self) -> None:
        """Clear state accumulated by the workload between runs."""
        ...
