from __future__ import annotations
from typing import List
from yt_dubber.models import SubtitleSegment


def should_synthesize(text: str) -> bool:
    """Return True if text has >= 3 alphabetic characters and is worth synthesizing.
    Symbol-only or very short cues return False; silence is used instead.
    Implemented in Phase 4.
    """
    raise NotImplementedError("tts.should_synthesize — implemented in Phase 4")


def synthesize_all(
    segments: List[SubtitleSegment],
    voice_id: str,
    output_dir: str,
    resume: bool = False,
) -> List[SubtitleSegment]:
    """Generate TTS audio for each segment with meaningful text.
    Saves .wav files to output_dir/segments/. Updates segment.audio_path and
    segment.status = SegmentStatus.TTS_DONE after each segment (resume support).
    Skipped segments get status = SegmentStatus.SKIPPED.
    Implemented in Phase 4.
    """
    raise NotImplementedError("tts.synthesize_all — implemented in Phase 4")
