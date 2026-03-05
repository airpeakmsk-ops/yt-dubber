from __future__ import annotations
import re
from typing import List

from yt_dubber.models import SubtitleSegment

_TIMECODE_RE = re.compile(
    r"(\d{2}):(\d{2}):(\d{2}),(\d{3})\s*-->\s*(\d{2}):(\d{2}):(\d{2}),(\d{3})"
)
_TAG_RE = re.compile(r"<[^>]+>")


def _ts_to_sec(h: str, m: str, s: str, ms: str) -> float:
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def parse_srt(content: str) -> List[SubtitleSegment]:
    """Parse SRT content string into a list of SubtitleSegment objects.

    Handles:
    - Standard SRT timecode format (HH:MM:SS,mmm --> HH:MM:SS,mmm)
    - Multi-line subtitle text (joined with space)
    - Residual VTT inline tags stripped (<c>, <00:00:01.000>, etc.)
    - Empty or malformed blocks silently skipped
    """
    segments: List[SubtitleSegment] = []
    blocks = re.split(r"\n\s*\n", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            idx = int(lines[0].strip())
        except ValueError:
            continue
        m = _TIMECODE_RE.match(lines[1].strip())
        if not m:
            continue
        start_sec = _ts_to_sec(m.group(1), m.group(2), m.group(3), m.group(4))
        end_sec   = _ts_to_sec(m.group(5), m.group(6), m.group(7), m.group(8))
        text = " ".join(lines[2:]).strip()
        text = _TAG_RE.sub("", text).strip()
        if not text:
            continue
        segments.append(SubtitleSegment(
            index=idx,
            start_sec=start_sec,
            end_sec=end_sec,
            duration_sec=round(end_sec - start_sec, 3),
            jp_text=text,
        ))
    return segments


def parse_srt_file(path: str) -> List[SubtitleSegment]:
    """Read an SRT file (UTF-8) and return parsed SubtitleSegment list."""
    with open(path, "r", encoding="utf-8") as f:
        return parse_srt(f.read())
