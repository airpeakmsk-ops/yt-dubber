from __future__ import annotations
from yt_dubber.models import JobState


def save(job: JobState, path: str) -> None:
    """Serialize JobState to JSON and write to path.
    Called after every TTS segment for fail-safe resume support.
    Implemented in Phase 4.
    """
    raise NotImplementedError("checkpoint.save — implemented in Phase 4")


def load(path: str) -> JobState:
    """Deserialize JobState from JSON file at path.
    Returns fully reconstructed JobState with SubtitleSegment list.
    Implemented in Phase 4.
    """
    raise NotImplementedError("checkpoint.load — implemented in Phase 4")
