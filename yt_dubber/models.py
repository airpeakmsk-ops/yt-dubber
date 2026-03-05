from __future__ import annotations
from dataclasses import dataclass, field
from typing import Optional
from enum import StrEnum


class SegmentStatus(StrEnum):
    PENDING    = "pending"
    TRANSLATED = "translated"
    APPROVED   = "approved"
    SKIPPED    = "skipped"
    TTS_DONE   = "tts_done"
    ERROR      = "error"


@dataclass
class SubtitleSegment:
    index:         int
    start_sec:     float          # always float seconds, never formatted strings
    end_sec:       float
    duration_sec:  float          # end_sec - start_sec (computed at construction time)
    jp_text:       str
    ru_text:       str = ""
    audio_path:    Optional[str] = None
    status:        SegmentStatus = SegmentStatus.PENDING
    error_message: Optional[str] = None


@dataclass
class JobState:
    video_id:    str
    video_title: str
    source_url:  str
    docx_path:   str
    output_dir:  str
    segments:    list[SubtitleSegment] = field(default_factory=list)
    phase:       str = "phase1"
    created_at:  str = ""
    updated_at:  str = ""
