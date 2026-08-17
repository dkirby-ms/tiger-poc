from collections.abc import AsyncIterator

import pytest
from pydantic import BaseModel

from apps.pipeline_framework import Envelope, PipelineRunner, StageContext, StageHealth, StageRegistry, load_pipeline
from apps.pipeline_framework.contracts import StageBase


class EmptyConfig(BaseModel):
    pass


class NumberSource(StageBase):
    async def produce(self) -> AsyncIterator[Envelope[int]]:
        for sequence in range(3):
            yield Envelope.create(
                stream_id="source",
                seq=sequence,
                captured_at=float(sequence),
                payload=sequence,
            )


class Doubler(StageBase):
    async def process(self, item: Envelope[int]) -> AsyncIterator[Envelope[int]]:
        yield item.derive(item.payload * 2)


class Collector(StageBase):
    def __init__(self, values: list[int]) -> None:
        super().__init__()
        self._values = values

    async def process(self, item: Envelope[int]) -> AsyncIterator[Envelope[None]]:
        self._values.append(item.payload)
        if False:
            yield item.derive(None)


def create_registry(values: list[int]) -> StageRegistry:
    registry = StageRegistry()
    registry.register("source.number", lambda config: NumberSource(), EmptyConfig, accepts=None, emits=int, source=True)
    registry.register("transform.double", lambda config: Doubler(), EmptyConfig, accepts=int, emits=int)
    registry.register("sink.collect", lambda config: Collector(values), EmptyConfig, accepts=int, emits=None)
    return registry


@pytest.mark.asyncio
async def test_given_valid_pipeline_when_run_then_values_arrive_in_order(tmp_path):
    # Arrange
    path = tmp_path / "pipeline.yaml"
    path.write_text(
        "apiVersion: tiger.dev/v1\n"
        "kind: Pipeline\n"
        "metadata: {name: runner-test}\n"
        "spec:\n"
        "  stages:\n"
        "    - {id: source, type: source.number}\n"
        "    - {id: double, type: transform.double, inputs: [source]}\n"
        "    - {id: sink, type: sink.collect, inputs: [double]}\n",
        encoding="utf-8",
    )
    values: list[int] = []
    registry = create_registry(values)
    runner = PipelineRunner(load_pipeline(path, registry), registry)

    # Act
    result = await runner.run()

    # Assert
    assert values == [0, 2, 4]
    assert all(health == StageHealth() for health in result.stage_health.values())
    assert result.channels["source->double"].sent == 3
    assert result.channels["double->sink"].received == 3


@pytest.mark.asyncio
async def test_given_fan_out_when_run_then_each_sink_receives_every_value(tmp_path):
    # Arrange
    path = tmp_path / "pipeline.yaml"
    path.write_text(
        "apiVersion: tiger.dev/v1\n"
        "kind: Pipeline\n"
        "metadata: {name: fanout-test}\n"
        "spec:\n"
        "  stages:\n"
        "    - {id: source, type: source.number}\n"
        "    - {id: left, type: sink.collect, inputs: [source]}\n"
        "    - {id: right, type: sink.collect, inputs: [source]}\n",
        encoding="utf-8",
    )
    values: list[int] = []
    registry = create_registry(values)
    runner = PipelineRunner(load_pipeline(path, registry), registry)

    # Act
    await runner.run()

    # Assert
    assert values == [0, 1, 2, 0, 1, 2]