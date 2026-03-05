from __future__ import annotations
from typing import List
from yt_dubber.models import SubtitleSegment


def has_japanese_subtitles(url: str) -> bool:
    """Check whether the video at url has Japanese subtitle tracks available.
    Returns True if manual or auto-generated Japanese subtitles exist.
    Implemented in Phase 2.
    """
    raise NotImplementedError("extractor.has_japanese_subtitles — implemented in Phase 2")


def download_subtitles(url: str, output_dir: str, lang: str = "ja") -> str:
    """Download subtitles for the given YouTube URL using yt-dlp.
    Returns the path to the downloaded .srt file.
    Implemented in Phase 2.
    """
    raise NotImplementedError("extractor.download_subtitles — implemented in Phase 2")


def extract_segments(url: str, output_dir: str) -> List[SubtitleSegment]:
    """Full extraction pipeline: download + parse + return SubtitleSegment list.
    Implemented in Phase 2.
    """
    raise NotImplementedError("extractor.extract_segments — implemented in Phase 2")
