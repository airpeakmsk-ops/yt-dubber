from __future__ import annotations
from typing import List
from yt_dubber.models import SubtitleSegment


def translate_segments(
    segments: List[SubtitleSegment],
    batch_size: int = 20,
    model: str | None = None,
) -> List[SubtitleSegment]:
    """Translate jp_text to ru_text for each segment using the Claude API.
    Processes in batches of batch_size. Updates segment.ru_text and
    segment.status = SegmentStatus.TRANSLATED in-place. Returns the updated list.
    Implemented in Phase 3.
    """
    raise NotImplementedError("translator.translate_segments — implemented in Phase 3")
