"""Asynchronous in-process execution for validated pipeline graphs."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from .channel import ChannelStats, InProcChannel
from .contracts import Envelope, Source, Stage, StageContext, StageHealth
from .manifest import LoadedPipeline
from .registry import StageRegistry


@dataclass(frozen=True)
class RunnerResult:
    stage_health: dict[str, StageHealth]
    channels: dict[str, ChannelStats]


class PipelineRunner:
    """Runs one validated pipeline and tears down initialized stages reliably."""

    def __init__(
        self,
        pipeline: LoadedPipeline,
        registry: StageRegistry,
        *,
        services: dict[str, Any] | None = None,
    ) -> None:
        self._pipeline = pipeline
        self._registry = registry
        self._services = services or {}

    async def run(self) -> RunnerResult:
        instances = {
            stage_id: self._registry.create(item.spec.type, item.config)
            for stage_id, item in self._pipeline.stages.items()
        }
        channels = self._create_channels()
        initialized: list[str] = []
        try:
            for stage_id in self._pipeline.order:
                await instances[stage_id].setup(
                    StageContext(stage_id=stage_id, services=self._services)
                )
                initialized.append(stage_id)
            tasks = []
            for stage_id in self._pipeline.order:
                item = self._pipeline.stages[stage_id]
                if item.definition.source:
                    coroutine = self._run_source(stage_id, instances[stage_id], channels)
                else:
                    coroutine = self._run_stage(stage_id, instances[stage_id], channels)
                tasks.append(asyncio.create_task(coroutine, name=stage_id))
            try:
                await asyncio.gather(*tasks)
            except BaseException:
                for task in tasks:
                    task.cancel()
                await asyncio.gather(*tasks, return_exceptions=True)
                raise
        finally:
            for stage_id in reversed(initialized):
                await instances[stage_id].teardown()
        return RunnerResult(
            stage_health={stage_id: stage.health() for stage_id, stage in instances.items()},
            channels={edge: channel.stats() for edge, channel in channels.items()},
        )

    def _create_channels(self) -> dict[str, InProcChannel]:
        defaults = self._pipeline.manifest.spec.defaults.channel
        channels: dict[str, InProcChannel] = {}
        for downstream_id, item in self._pipeline.stages.items():
            config = item.spec.channel or defaults
            for upstream_id in item.spec.inputs:
                edge = self._edge(upstream_id, downstream_id)
                channels[edge] = InProcChannel(
                    capacity=config.capacity,
                    on_full=config.on_full,
                    sample_every=config.sample_every,
                )
        return channels

    async def _run_source(
        self,
        stage_id: str,
        source: Source,
        channels: dict[str, InProcChannel],
    ) -> None:
        try:
            async for envelope in source.produce():
                await self._publish(stage_id, envelope, channels)
        finally:
            await self._close_outputs(stage_id, channels)

    async def _run_stage(
        self,
        stage_id: str,
        stage: Stage,
        channels: dict[str, InProcChannel],
    ) -> None:
        upstream_id = self._pipeline.stages[stage_id].spec.inputs[0]
        inbound = channels[self._edge(upstream_id, stage_id)]
        try:
            async for envelope in inbound.receive():
                async for output in stage.process(envelope):
                    await self._publish(stage_id, output, channels)
        finally:
            await self._close_outputs(stage_id, channels)

    async def _publish(
        self,
        stage_id: str,
        envelope: Envelope,
        channels: dict[str, InProcChannel],
    ) -> None:
        for edge, channel in channels.items():
            if edge.startswith(f"{stage_id}->"):
                await channel.send(envelope)

    async def _close_outputs(
        self, stage_id: str, channels: dict[str, InProcChannel]
    ) -> None:
        for edge, channel in channels.items():
            if edge.startswith(f"{stage_id}->"):
                await channel.close()

    @staticmethod
    def _edge(upstream_id: str, downstream_id: str) -> str:
        return f"{upstream_id}->{downstream_id}"