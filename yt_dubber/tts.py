from __future__ import annotations

import os
import time
import wave
from typing import List, Optional

from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings
from elevenlabs.core.api_error import ApiError

from yt_dubber.models import SubtitleSegment, SegmentStatus, JobState
from yt_dubber.config import settings
from yt_dubber import checkpoint


# Exponential backoff schedule (seconds). 5 entries = max 5 attempts total.
BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]


def should_synthesize(text: str) -> bool:
    """Return True if text has >= 3 alphabetic characters and is worth synthesizing.

    Symbol-only or very short cues (< 3 alpha chars) return False; silence is
    generated instead to avoid wasting ElevenLabs quota on non-speech content.
    """
    return sum(1 for c in text if c.isalpha()) >= 3


def _write_pcm_as_wav(pcm_bytes: bytes, path: str) -> None:
    """Wrap raw S16LE PCM bytes in a proper WAV container and write to path."""
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(pcm_bytes)


def _write_silence(path: str, duration_sec: float) -> None:
    """Write a silent mono 22050 Hz 16-bit WAV of the given duration."""
    sample_rate = 22050
    n_frames = int(sample_rate * duration_sec)
    silence = b"\x00" * (n_frames * 2)  # 1 channel x 2 bytes (16-bit S16LE)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(22050)
        wf.writeframes(silence)


def _synthesize_segment(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str,
    stability: float,
    similarity_boost: float,
) -> bytes:
    """Call ElevenLabs TTS and return raw PCM bytes.

    PITFALL: SDK returns an iterator, NOT bytes. Must collect via b"".join().
    """
    audio_iter = client.text_to_speech.convert(
        text=text,
        voice_id=voice_id,
        model_id=model_id,
        output_format="pcm_22050",
        voice_settings=VoiceSettings(stability=stability, similarity_boost=similarity_boost),
    )
    return b"".join(audio_iter)


def _call_with_retry(
    client: ElevenLabs,
    text: str,
    voice_id: str,
    model_id: str,
    stability: float,
    similarity_boost: float,
) -> bytes:
    """Call _synthesize_segment with exponential-backoff retry on ApiError.

    Retry schedule: [5, 10, 20, 40, 80] seconds (5 attempts total).
    If a 429 response includes a Retry-After header, that value overrides
    the schedule. After all attempts are exhausted, the final ApiError is
    re-raised so the caller can mark the segment as ERROR.
    """
    for attempt, wait_default in enumerate(BACKOFF_SCHEDULE):
        try:
            return _synthesize_segment(
                client, text, voice_id, model_id, stability, similarity_boost
            )
        except ApiError as exc:
            if attempt < len(BACKOFF_SCHEDULE) - 1:
                # Determine wait time: honour Retry-After header when present
                retry_after = None
                try:
                    if exc.headers is not None:
                        retry_after = exc.headers.get("Retry-After")
                except AttributeError:
                    pass

                if exc.status_code == 429 and retry_after:
                    wait = float(retry_after)
                else:
                    wait = float(wait_default)

                print(
                    f"... attempt {attempt + 2}/{len(BACKOFF_SCHEDULE)}, "
                    f"waiting {wait:.0f}s..."
                )
                time.sleep(wait)
            else:
                raise  # propagate after last attempt


def synthesize_all(
    segments: List[SubtitleSegment],
    voice_id: str,
    output_dir: str,
    resume: bool = False,
    job: Optional[JobState] = None,
    checkpoint_path: Optional[str] = None,
) -> List[SubtitleSegment]:
    """Generate TTS audio for each segment with meaningful Russian text.

    Saves .wav files to output_dir/segments/. Updates segment.audio_path and
    segment.status = SegmentStatus.TTS_DONE after each segment (resume support).
    Skipped segments (should_synthesize() is False) get status = SKIPPED with
    a silence clip of matching duration.

    Args:
        segments:        List of SubtitleSegment to process.
        voice_id:        ElevenLabs voice ID to use.
        output_dir:      Root output directory; WAVs written to output_dir/segments/.
        resume:          If True, skip segments with status=TTS_DONE.
        job:             Optional JobState for checkpointing.
        checkpoint_path: Optional path for checkpoint JSON; required with job.

    Returns:
        The same segments list with updated status and audio_path fields.
    """
    segments_dir = os.path.join(output_dir, "segments")
    os.makedirs(segments_dir, exist_ok=True)

    client = ElevenLabs(api_key=settings.elevenlabs_api_key)
    total = len(segments)

    for seg in segments:
        filename = f"seg_{seg.index:04d}.wav"
        path = os.path.join(segments_dir, filename)

        # Resume: skip already-successful segments
        if resume and seg.status == SegmentStatus.TTS_DONE:
            print(f"[{seg.index:02d}/{total}] {filename} — RESUME SKIP (already done)")
            continue

        if not should_synthesize(seg.ru_text):
            # Write silence instead of calling API
            _write_silence(path, seg.duration_sec)
            seg.audio_path = path
            seg.status = SegmentStatus.SKIPPED
            print(f"[{seg.index:02d}/{total}] {filename} — SKIPPED (silence)")
        else:
            try:
                pcm_bytes = _call_with_retry(
                    client,
                    seg.ru_text,
                    voice_id,
                    settings.elevenlabs_model,
                    settings.elevenlabs_stability,
                    settings.elevenlabs_similarity_boost,
                )
                _write_pcm_as_wav(pcm_bytes, path)
                seg.audio_path = path
                seg.status = SegmentStatus.TTS_DONE
                print(f"[{seg.index:02d}/{total}] {filename} — OK")
            except ApiError as exc:
                seg.status = SegmentStatus.ERROR
                seg.error_message = str(exc)
                print(f"[{seg.index:02d}/{total}] {filename} — ERROR: {exc}")

        # Checkpoint after every segment regardless of outcome
        if job is not None and checkpoint_path is not None:
            checkpoint.save(job, checkpoint_path)

    return segments
