from __future__ import annotations


def stretch_to_duration(audio_path: str, target_ms: int) -> bytes:
    """Time-stretch or compress the audio at audio_path to target_ms milliseconds.
    Clamps stretch ratio to 0.60x-1.75x quality range.
    Uses pyrubberband if available, falls back to librosa.
    Returns stretched audio as WAV bytes.
    Implemented in Phase 5.
    """
    raise NotImplementedError("audio_sync.stretch_to_duration — implemented in Phase 5")
