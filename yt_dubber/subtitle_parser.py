from __future__ import annotations
from typing import List
from yt_dubber.models import SubtitleSegment


def parse_srt(content: str) -> List[SubtitleSegment]:
    """Parse SRT file content into a list of SubtitleSegment objects.
    Timecodes stored as float seconds. Deduplicates rolling-window VTT artifacts.
    Implemented in Phase 2.
    """
    raise NotImplementedError("subtitle_parser.parse_srt — implemented in Phase 2")


def parse_srt_file(path: str) -> List[SubtitleSegment]:
    """Read .srt file at path and return parsed SubtitleSegment list.
    Reads with encoding='utf-8'. Implemented in Phase 2.
    """
    raise NotImplementedError("subtitle_parser.parse_srt_file — implemented in Phase 2")
