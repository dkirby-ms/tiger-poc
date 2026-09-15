"""Thin Fabric PySpark/Delta adapter for tested curation decisions.

Run this module only in a Fabric notebook runtime with PySpark and Delta available.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from tiger_poc.fabric.curation import curate_records


def curate_raw_process_events(spark: Any, *, table_root: str = "Tables") -> dict[str, int]:
    """Curate raw Delta rows into idempotent history and station current state.

    Args:
        spark: Active Fabric Spark session.
        table_root: Lakehouse Delta table root.

    Returns:
        Counts of accepted history, current-state, and rejected rows.
    """
    from delta.tables import DeltaTable

    raw_rows = [row.asDict(recursive=True) for row in spark.table("raw_process_events").collect()]
    existing_event_ids = {
        row.eventId for row in spark.table("process_events").select("eventId").collect()
    }
    current_sequences = {
        row.stationId: row.sequence
        for row in spark.table("stations_current").select("stationId", "sequence").collect()
    }
    result = curate_records(
        raw_rows,
        existing_event_ids=existing_event_ids,
        current_sequences=current_sequences,
    )

    if result.history_rows:
        history_source = spark.createDataFrame(list(result.history_rows))
        history_target = DeltaTable.forPath(spark, f"{table_root}/process_events")
        history_target.alias("target").merge(
            history_source.alias("source"), "target.eventId = source.eventId"
        ).whenNotMatchedInsertAll().execute()

    if result.current_rows:
        current_source = spark.createDataFrame(list(result.current_rows))
        current_target = DeltaTable.forPath(spark, f"{table_root}/stations_current")
        current_target.alias("target").merge(
            current_source.alias("source"), "target.stationId = source.stationId"
        ).whenMatchedUpdateAll(
            condition="source.sequence > target.sequence"
        ).whenNotMatchedInsertAll().execute()

    if result.rejected_rows:
        rejected_source = spark.createDataFrame(
            [
                {
                    **asdict(row),
                    "reason": row.reason.value if hasattr(row.reason, "value") else row.reason,
                }
                for row in result.rejected_rows
            ]
        )
        rejected_source.write.format("delta").mode("append").save(
            f"{table_root}/rejected_process_events"
        )

    return {
        "history": len(result.history_rows),
        "current": len(result.current_rows),
        "rejected": len(result.rejected_rows),
    }
