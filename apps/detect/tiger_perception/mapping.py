"""Map a resolved boolean observation to the existing versioned event schema."""

import re
from datetime import UTC, datetime

from .config import Workload
from .contracts import Observation, ProcessEvent
from .sinks import validate_process_event


def map_presence(observation: Observation, workload: Workload) -> dict[str, object]:
    """Preserve observation identity on retries and attach deployment metadata."""
    source = workload.spec.source
    if (observation.subject_resolution != "resolved"
            or observation.subject_id != source.subjectId
            or observation.source_id != source.id
            or type(observation.value) is not bool
            or observation.observation_type != workload.spec.perception.observationType):
        raise ValueError("Only a resolved boolean observation for this workload can be mapped")
    event = ProcessEvent(
        event_id=observation.observation_id, source_id=source.id,
        subject_id=source.subjectId, observation_type=observation.observation_type,
        value=observation.value, unit="boolean", confidence=observation.confidence,
        captured_at=observation.captured_at, produced_at=observation.produced_at,
        published_at=datetime.now(UTC).isoformat(), provider=observation.provider,
        model=observation.model, source=source.type, observation=observation.metadata,
    ).to_dict()
    event.update(plantId=workload.metadata.plantId, plantName=workload.metadata.plantName)
    return validate_process_event(event)


def map_identification(observation: Observation, workload: Workload) -> dict[str, object]:
    """Publish positive case identification, never infer physical removal from unreadable QR."""
    if (workload.spec.perception.provider != "qr"
            or observation.observation_type != "BoxIdentified"
            or observation.source_id != workload.spec.source.id
            or observation.subject_resolution != "resolved"
            or not re.fullmatch(r"CASE-[0-9]{3}", observation.subject_id or "")
            or observation.value is not True):
        raise ValueError("Only a confirmed QR case identification can be mapped")
    event = ProcessEvent(
        event_id=observation.observation_id, source_id=observation.source_id,
        subject_id=observation.subject_id, observation_type="BoxIdentified",
        value=observation.subject_id, unit="identifier", confidence=observation.confidence,
        captured_at=observation.captured_at, produced_at=observation.produced_at,
        published_at=datetime.now(UTC).isoformat(), provider=observation.provider,
        model=observation.model, source=workload.spec.source.type,
        observation={**observation.metadata, "positionId": workload.spec.source.subjectId,
                     "confidenceMeaning": "decoded-payload-not-probability"},
    ).to_dict()
    event.update(plantId=workload.metadata.plantId, plantName=workload.metadata.plantName)
    return validate_process_event(event)