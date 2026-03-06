from __future__ import annotations

import io
import os
import wave
from typing import List, Optional

import numpy as np
import soundfile as sf

from yt_dubber.models import SubtitleSegment, SegmentStatus, JobState
from yt_dubber.config import settings
from yt_dubber.audio_sync import stretch_to_duration

SAMPLE_RATE: int = 22050

try:
    import lameenc as _lameenc
    _LAMEENC_AVAILABLE = True
except ImportError:
    _lameenc = None  # type: ignore[assignment]
    _LAMEENC_AVAILABLE = False


def _encode_mp3(canvas: np.ndarray) -> bytes:
    """Encode int16 numpy array to MP3 bytes using lameenc.

    Falls back to raw WAV bytes if lameenc is unavailable (e.g. Python 3.14
    where no cp314 wheels are published).  The fallback emits a warning so
    callers know the "mp3" file is actually a WAV container.

    Args:
        canvas: 1D int16 numpy array at SAMPLE_RATE Hz (22050 Hz, mono).

    Returns:
        MP3 bytes (lameenc) or WAV bytes (fallback).
    """
    if _LAMEENC_AVAILABLE:
        encoder = _lameenc.Encoder()
        encoder.set_bit_rate(192)
        encoder.set_in_sample_rate(SAMPLE_RATE)
        encoder.set_channels(1)
        encoder.set_quality(2)
        mp3_data = encoder.encode(canvas.tobytes())
        mp3_data += encoder.flush()
        return mp3_data

    # Fallback: write WAV to bytes buffer — lameenc not available
    print("WARN: lameenc not available — output written as WAV (not MP3)")
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(canvas.tobytes())
    buf.seek(0)
    return buf.read()


def assemble_track(
    segments: List[SubtitleSegment],
    total_ms: Optional[int] = None,
    output_path: Optional[str] = None,
    fmt: str = "mp3",
    stretch: bool = True,
    job: Optional[JobState] = None,
) -> str:
    """Assemble dubbed audio track from TTS segments using absolute timecode positions.

    Each TTS_DONE or SKIPPED segment with a valid audio_path is stretched to its
    subtitle slot duration and placed at start_sec in a pre-allocated silence canvas.
    ERROR segments and segments with audio_path=None produce silence at their timecode.
    The canvas is encoded to MP3 at 192 kbps via lameenc (no ffmpeg required).

    Args:
        segments:    List of SubtitleSegment with TTS results from Phase 4.
        total_ms:    Total track length in ms. If None, auto-computed from
                     int(max(seg.end_sec for seg in segments) * 1000).
        output_path: Output file path. If None, derived from job.video_id and
                     settings.output_dir as "{output_dir}/{video_id}_dubbed_ru.mp3".
        fmt:         Output format (default "mp3" — only mp3 currently supported).
        stretch:     If True, time-stretch each segment to its slot. If False,
                     place at native speed (future use; currently always stretch).
        job:         Optional JobState for deriving default output_path.

    Returns:
        Absolute path to the written MP3 file.
    """
    # Compute total track length
    if total_ms is None:
        total_ms = int(max(seg.end_sec for seg in segments) * 1000)

    # Derive default output path
    if output_path is None:
        video_id = job.video_id if job is not None else "output"
        output_path = os.path.join(settings.output_dir, f"{video_id}_dubbed_ru.mp3")

    # Ensure output directory exists
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Select active segments (skip ERROR and None audio_path)
    active = [
        seg for seg in segments
        if seg.audio_path is not None
        and seg.status in (SegmentStatus.TTS_DONE, SegmentStatus.SKIPPED)
    ]

    print(f"Assembling {len(active)} segments...")

    # Allocate silence canvas
    total_samples = int(total_ms * SAMPLE_RATE / 1000)
    canvas = np.zeros(total_samples, dtype=np.int16)

    for seg in active:
        target_ms = int(seg.duration_sec * 1000)

        # Stretch segment to fit its subtitle slot
        wav_bytes = stretch_to_duration(seg.audio_path, target_ms, index=seg.index)

        # Read stretched WAV as int16 array
        seg_arr, _ = sf.read(io.BytesIO(wav_bytes), dtype="int16", always_2d=False)

        # Place at absolute timecode position
        start = int(seg.start_sec * SAMPLE_RATE)
        end = start + len(seg_arr)

        # Canvas boundary guard: truncate if overrun
        if end > total_samples:
            seg_arr = seg_arr[:total_samples - start]
            end = total_samples

        # Slice-assign (not += to avoid int16 overflow on overlap)
        canvas[start:end] = seg_arr

    # Encode to MP3 via lameenc (no ffmpeg) or WAV fallback
    audio_data = _encode_mp3(canvas)

    with open(output_path, "wb") as f:
        f.write(audio_data)

    print(f"Done: {output_path}")
    return output_path
