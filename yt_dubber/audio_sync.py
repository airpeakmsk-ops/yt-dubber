from __future__ import annotations

import io

import numpy as np
import soundfile as sf
import librosa

SAMPLE_RATE: int = 22050
RATIO_MIN: float = 0.60   # maximum compression (below -> clamp to 0.60x, pad silence)
RATIO_MAX: float = 1.75   # maximum stretch (above -> native speed, pad silence)


def _time_stretch(y: np.ndarray, rate: float, sr: int) -> np.ndarray:
    """Stretch y by rate (rate>1 = speed up, rate<1 = slow down).
    Uses pyrubberband if available; falls back to librosa on any exception."""
    try:
        import pyrubberband as pyrb
        return pyrb.time_stretch(y, sr, rate)
    except Exception:
        return librosa.effects.time_stretch(y, rate=rate)


def stretch_to_duration(audio_path: str, target_ms: int, index: int = 0) -> bytes:
    """Time-stretch audio at audio_path to target_ms milliseconds.

    Rules (per CONTEXT.md locked decisions):
    - ratio = tts_ms / target_ms
    - ratio > RATIO_MAX: native speed + silence pad, emit WARN
    - ratio < RATIO_MIN: clamp to RATIO_MIN + silence pad, emit WARN
    - else: time_stretch(y, ratio)
    - Output is exactly int(target_ms * SAMPLE_RATE / 1000) samples, returned as WAV bytes.

    Args:
        audio_path: Path to input WAV file (mono or stereo, any sample rate).
        target_ms:  Target duration in milliseconds.
        index:      Segment index for WARN log formatting (default 0).

    Returns:
        WAV bytes of exactly target_ms duration at SAMPLE_RATE / mono / PCM_16.
    """
    # Read input audio
    y, sr = sf.read(audio_path, dtype="float32", always_2d=False)

    # Force mono
    if y.ndim > 1:
        y = y[:, 0]

    # Resample if source rate differs (ElevenLabs outputs 22050, but guard anyway)
    if sr != SAMPLE_RATE:
        y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)

    tts_ms = len(y) / SAMPLE_RATE * 1000
    ratio = tts_ms / target_ms  # < 1 = slow down, > 1 = speed up

    if ratio > RATIO_MAX:
        # TTS too long relative to slot: play at native speed, pad remainder
        print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x -> 1.00x)")
        stretched = y
    elif ratio < RATIO_MIN:
        # TTS too short relative to slot: clamp compression at RATIO_MIN
        print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x -> {RATIO_MIN:.2f}x)")
        # Short segment guard: skip time_stretch below librosa FFT minimum
        if len(y) < 512:
            stretched = y
        else:
            stretched = _time_stretch(y, RATIO_MIN, SAMPLE_RATE)
    else:
        # Normal range: stretch/compress to fill slot exactly
        if len(y) < 512:
            stretched = y
        else:
            stretched = _time_stretch(y, ratio, SAMPLE_RATE)

    # Trim or pad to exactly target_ms samples
    target_samples = int(target_ms * SAMPLE_RATE / 1000)
    if len(stretched) >= target_samples:
        out = stretched[:target_samples]
    else:
        pad = np.zeros(target_samples - len(stretched), dtype=np.float32)
        out = np.concatenate([stretched, pad])

    # Encode to WAV bytes
    buf = io.BytesIO()
    sf.write(buf, out, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()
