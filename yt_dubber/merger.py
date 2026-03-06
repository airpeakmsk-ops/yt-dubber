from __future__ import annotations

import io
import os
from typing import List, Optional

import numpy as np
import soundfile as sf

from yt_dubber.models import SubtitleSegment, SegmentStatus, JobState
from yt_dubber.config import settings
from yt_dubber.audio_sync import stretch_to_duration

SAMPLE_RATE: int = 22050


def assemble_track(
    segments: List[SubtitleSegment],
    total_ms: Optional[int] = None,
    output_path: Optional[str] = None,
    fmt: str = "mp3",
    stretch: bool = True,
    job: Optional[JobState] = None,
) -> str:
    """Assemble dubbed audio track from TTS segments using absolute timecode positions.
    Each segment is stretched to its subtitle slot duration, then placed at
    segment.start_sec * 1000 ms in the output track (no cumulative drift).
    Silence is inserted for skipped or failed segments.
    Returns output_path of the final MP3/WAV file.
    Implemented in Phase 5.
    """
    raise NotImplementedError("merger.assemble_track — implemented in Phase 5")
