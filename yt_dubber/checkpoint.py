from __future__ import annotations

import json
import dataclasses

from yt_dubber.models import JobState, SubtitleSegment, SegmentStatus


def save(job: JobState, path: str) -> None:
    """Serialize JobState to JSON and write to path.

    Called after every TTS segment for fail-safe resume support.
    Uses dataclasses.asdict() for serialization; SegmentStatus StrEnum values
    serialize naturally as their string values.
    """
    data = dataclasses.asdict(job)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def load(path: str) -> JobState:
    """Deserialize JobState from JSON file at path.

    Returns fully reconstructed JobState with SubtitleSegment list.

    CRITICAL: data["segments"] is a list of plain dicts after JSON deserialization.
    Each dict must be explicitly converted back to a SubtitleSegment with
    SegmentStatus reconstructed from its string value via SegmentStatus(str_val).
    Simply calling JobState(**data) without this step would leave segments as plain
    dicts, causing AttributeError when downstream code accesses .status, .audio_path, etc.
    """
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    data["segments"] = [
        SubtitleSegment(
            **{**s, "status": SegmentStatus(s["status"])}
        )
        for s in data["segments"]
    ]

    return JobState(**data)
