"""Group consecutive ride steps on the same line into one segment for the client.

The router emits one ride step per stop pair; the UI wants one segment per
line, with stop count, summed distance/duration and the wait only once.
"""
from __future__ import annotations

from typing import Any


def group_steps(
    steps: list[dict[str, Any]],
    line_labels: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Merge consecutive rides on the same line into a single ride segment.

    A walk (or any non-ride step) breaks the run, as does a change of line.
    The merged segment keeps the first wait (boarding happens once) and sums
    the per-hop ride time and distance.
    """
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for step in steps:
        if step.get("type") != "ride":
            out.append(step)
            current = None
            continue
        line = step.get("line") or ""
        if current is None or current.get("line") != line:
            # Start a new segment; copy so caller data is not mutated.
            seg = dict(step)
            seg["stops"] = 1
            seg["ride_min"] = 0.0
            # ride_min is the driving time without the boarding wait.
            seg["ride_min"] = round(
                float(step.get("duration_min") or 0.0) - float(step.get("wait_min") or 0.0),
                3,
            )
            labels = line_labels or {}
            if line in labels and isinstance(labels[line], dict):
                if labels[line].get("label") is not None:
                    seg["line_label"] = labels[line]["label"]
                if labels[line].get("operator") is not None:
                    seg["line_operator"] = labels[line]["operator"]
            out.append(seg)
            current = seg
            continue
        # Continue the current segment: extend to this hop's end.
        current["to_name"] = step.get("to_name", current.get("to_name"))
        current["to"] = step.get("to", current.get("to"))
        current["to_id"] = step.get("to_id", current.get("to_id"))
        current["stops"] = int(current.get("stops") or 1) + 1
        current["distance_m"] = float(current.get("distance_m") or 0.0) + float(
            step.get("distance_m") or 0.0
        )
        hop_ride_min = float(step.get("duration_min") or 0.0) - float(
            step.get("wait_min") or 0.0
        )
        current["ride_min"] = round(float(current.get("ride_min") or 0.0) + hop_ride_min, 3)
        current["duration_min"] = round(
            float(current.get("ride_min") or 0.0) + float(current.get("wait_min") or 0.0),
            1,
        )
    return out
