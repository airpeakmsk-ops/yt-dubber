from __future__ import annotations
from typing import List, Dict
from yt_dubber.models import SubtitleSegment


def write_review_docx(
    segments: List[SubtitleSegment],
    output_path: str,
) -> str:
    """Write a 4-column review DOCX table: #, timecode, JP original, RU translation.
    Returns the output_path. Implemented in Phase 3.
    """
    raise NotImplementedError("docx_exporter.write_review_docx — implemented in Phase 3")


def read_review_docx(path: str) -> Dict[int, str]:
    """Read back user-edited Russian translations from the DOCX review table.
    Returns dict mapping segment index -> edited Russian text.
    Implemented in Phase 3.
    """
    raise NotImplementedError("docx_exporter.read_review_docx — implemented in Phase 3")
