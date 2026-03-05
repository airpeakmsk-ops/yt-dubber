from __future__ import annotations
from typing import List
from yt_dubber.models import SubtitleSegment


def assemble_track(
    segments: List[SubtitleSegment],
    total_ms: int,
    output_path: str,
    fmt: str = "mp3",
    stretch: bool = True,
) -> str:
    """Assemble dubbed audio track from TTS segments using absolute timecode positions.
    Each segment is stretched to its subtitle slot duration, then placed at
    segment.start_sec * 1000 ms in the output track (no cumulative drift).
    Silence is inserted for skipped or failed segments.
    Returns output_path of the final MP3/WAV file.
    Implemented in Phase 5.
    """
    raise NotImplementedError("merger.assemble_track — implemented in Phase 5")
