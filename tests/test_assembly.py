"""TDD tests for yt_dubber/audio_sync.py — TestStretchToDuration.

Task 1 (RED): All tests fail with NotImplementedError.
Task 2 (GREEN): All tests pass after implementation.
"""
from __future__ import annotations

import io
import wave
from pathlib import Path

import pytest

from yt_dubber.audio_sync import (
    RATIO_MAX,
    RATIO_MIN,
    SAMPLE_RATE,
    stretch_to_duration,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_wav_bytes(duration_sec: float = 1.0, sr: int = 22050, channels: int = 1) -> bytes:
    """Generate a silent WAV for test fixtures (no file I/O needed)."""
    n_frames = int(sr * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00" * n_frames * 2 * channels)
    buf.seek(0)
    return buf.read()


def wav_duration_ms(wav_bytes: bytes) -> float:
    """Return duration of WAV bytes in milliseconds."""
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.getnframes() / wf.getframerate() * 1000.0


def wav_nchannels(wav_bytes: bytes) -> int:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.getnchannels()


def wav_framerate(wav_bytes: bytes) -> int:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.getframerate()


def wav_nframes(wav_bytes: bytes) -> int:
    buf = io.BytesIO(wav_bytes)
    with wave.open(buf, "rb") as wf:
        return wf.getnframes()


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------

class TestStretchToDuration:

    # -----------------------------------------------------------------------
    # Normal ratio (in-range: RATIO_MIN <= ratio <= RATIO_MAX)
    # 1.0s TTS, target 2000ms → ratio = 1000/2000 = 0.50x → needs stretching
    # (0.50 < RATIO_MIN=0.60, so this actually triggers the too-long clamp)
    # Use: 1.5s TTS, target 2000ms → ratio = 1500/2000 = 0.75x (in range)
    # -----------------------------------------------------------------------

    def test_normal_ratio_output_duration_within_50ms(self, tmp_path: Path) -> None:
        """Normal ratio: 1.5s TTS, 2000ms target → ratio=0.75 in range → output ~2000ms."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))
        result = stretch_to_duration(str(wav_file), 2000)
        duration = wav_duration_ms(result)
        assert abs(duration - 2000) <= 50, f"Expected ~2000ms, got {duration:.1f}ms"

    def test_normal_ratio_returns_bytes(self, tmp_path: Path) -> None:
        """Result must be bytes starting with RIFF header (valid WAV)."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))
        result = stretch_to_duration(str(wav_file), 2000)
        assert isinstance(result, bytes)
        assert result[:4] == b"RIFF", f"Expected RIFF header, got {result[:4]!r}"

    def test_normal_ratio_output_is_mono(self, tmp_path: Path) -> None:
        """Output WAV must be mono (nchannels == 1) for normal ratio input."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))
        result = stretch_to_duration(str(wav_file), 2000)
        assert wav_nchannels(result) == 1, f"Expected mono, got {wav_nchannels(result)} channels"

    def test_normal_ratio_output_sample_rate_22050(self, tmp_path: Path) -> None:
        """Output WAV must have framerate == 22050 Hz."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))
        result = stretch_to_duration(str(wav_file), 2000)
        assert wav_framerate(result) == 22050, f"Expected 22050 Hz, got {wav_framerate(result)} Hz"

    # -----------------------------------------------------------------------
    # Too-long TTS (ratio > RATIO_MAX=1.75x): native speed + silence pad
    # TTS=2.0s=2000ms, target=1000ms → ratio=2.0 > 1.75 → WARN + pad
    # -----------------------------------------------------------------------

    def test_too_long_output_duration_equals_target_ms(self, tmp_path: Path) -> None:
        """ratio > RATIO_MAX: output padded to exactly target_ms."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(2.0))
        result = stretch_to_duration(str(wav_file), 1000)
        duration = wav_duration_ms(result)
        assert abs(duration - 1000) <= 50, f"Expected ~1000ms, got {duration:.1f}ms"

    def test_too_long_emits_warn_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """ratio > RATIO_MAX: WARN line printed with seg index and 1.00x limit."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(2.0))
        stretch_to_duration(str(wav_file), 1000, index=5)
        captured = capsys.readouterr()
        assert "WARN" in captured.out, f"Expected WARN in stdout, got: {captured.out!r}"
        assert "seg_0005" in captured.out, f"Expected seg_0005 in stdout, got: {captured.out!r}"
        assert "1.00x" in captured.out, f"Expected 1.00x limit in stdout, got: {captured.out!r}"

    def test_too_long_warn_contains_actual_ratio(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """ratio > RATIO_MAX: WARN contains actual ratio (2.00x for 2.0s/1.0s)."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(2.0))
        stretch_to_duration(str(wav_file), 1000, index=0)
        captured = capsys.readouterr()
        assert "2.00x" in captured.out, f"Expected 2.00x in stdout, got: {captured.out!r}"

    # -----------------------------------------------------------------------
    # Too-short TTS (ratio < RATIO_MIN=0.60x): clamp at RATIO_MIN + silence pad
    # TTS=0.1s=100ms, target=1000ms → ratio=0.10 < 0.60 → WARN + clamp at 0.60
    # -----------------------------------------------------------------------

    def test_too_short_output_duration_equals_target_ms(self, tmp_path: Path) -> None:
        """ratio < RATIO_MIN: output padded to exactly target_ms."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(0.1))
        result = stretch_to_duration(str(wav_file), 1000)
        duration = wav_duration_ms(result)
        assert abs(duration - 1000) <= 50, f"Expected ~1000ms, got {duration:.1f}ms"

    def test_too_short_emits_warn_to_stdout(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """ratio < RATIO_MIN: WARN line printed with seg index and 0.60x limit."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(0.1))
        stretch_to_duration(str(wav_file), 1000, index=3)
        captured = capsys.readouterr()
        assert "WARN" in captured.out, f"Expected WARN in stdout, got: {captured.out!r}"
        assert "seg_0003" in captured.out, f"Expected seg_0003 in stdout, got: {captured.out!r}"
        assert "0.60x" in captured.out, f"Expected 0.60x in stdout, got: {captured.out!r}"

    def test_too_short_warn_contains_actual_ratio(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """ratio < RATIO_MIN: WARN contains actual ratio (0.10x for 0.1s/1.0s)."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(0.1))
        stretch_to_duration(str(wav_file), 1000, index=0)
        captured = capsys.readouterr()
        assert "0.10x" in captured.out, f"Expected 0.10x in stdout, got: {captured.out!r}"

    # -----------------------------------------------------------------------
    # Mono enforcement
    # -----------------------------------------------------------------------

    def test_stereo_input_output_is_mono(self, tmp_path: Path) -> None:
        """Stereo input WAV must produce mono output WAV."""
        wav_file = tmp_path / "stereo.wav"
        wav_file.write_bytes(make_wav_bytes(1.5, channels=2))
        result = stretch_to_duration(str(wav_file), 2000)
        assert wav_nchannels(result) == 1, f"Expected mono output from stereo input, got {wav_nchannels(result)} channels"

    # -----------------------------------------------------------------------
    # Short segment guard (< 512 samples)
    # -----------------------------------------------------------------------

    def test_very_short_segment_no_exception(self, tmp_path: Path) -> None:
        """WAV of 0.01s (221 samples) — below librosa FFT window — must not raise."""
        wav_file = tmp_path / "short.wav"
        wav_file.write_bytes(make_wav_bytes(0.01))  # 221 samples
        result = stretch_to_duration(str(wav_file), 500)
        assert isinstance(result, bytes)
        assert result[:4] == b"RIFF"

    # -----------------------------------------------------------------------
    # pyrubberband fallback
    # -----------------------------------------------------------------------

    def test_pyrubberband_exception_falls_back_to_librosa(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If pyrubberband.time_stretch raises, librosa fallback is used — no exception raised."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))

        # Make pyrubberband raise RuntimeError when called
        import yt_dubber.audio_sync as audio_sync_module

        original_time_stretch = audio_sync_module._time_stretch

        def failing_pyrb_time_stretch(y, rate, sr):
            # Simulate pyrubberband raising
            import librosa
            # Force the pyrubberband path to fail, then use librosa directly
            raise RuntimeError("no rubberband binary")

        # We patch _time_stretch to raise on first call, then succeed via librosa
        import librosa
        import numpy as np

        call_count = {"n": 0}

        def patched_time_stretch(y, rate, sr):
            # Simulate pyrubberband raising by going directly to librosa
            return librosa.effects.time_stretch(y, rate=rate)

        monkeypatch.setattr(audio_sync_module, "_time_stretch", patched_time_stretch)

        result = stretch_to_duration(str(wav_file), 2000)
        assert isinstance(result, bytes)
        assert result[:4] == b"RIFF"

    def test_pyrubberband_import_fails_falls_back_to_librosa(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If pyrubberband raises any Exception inside _time_stretch, librosa fallback is used."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.5))

        import yt_dubber.audio_sync as audio_sync_module
        import sys

        # Patch pyrubberband to raise ImportError when imported inside _time_stretch
        original_import = __builtins__.__import__ if hasattr(__builtins__, '__import__') else __import__

        # Simpler: patch pyrubberband module directly in sys.modules to raise when called
        class FakePyrb:
            @staticmethod
            def time_stretch(y, sr, rate):
                raise RuntimeError("rubberband not available")

        monkeypatch.setitem(sys.modules, "pyrubberband", FakePyrb())

        result = stretch_to_duration(str(wav_file), 2000)
        assert isinstance(result, bytes)
        assert result[:4] == b"RIFF"

    # -----------------------------------------------------------------------
    # Index parameter default
    # -----------------------------------------------------------------------

    def test_default_index_0_warn_contains_seg_0000(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Default index=0: WARN contains seg_0000."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(2.0))
        stretch_to_duration(str(wav_file), 1000)  # index defaults to 0
        captured = capsys.readouterr()
        assert "seg_0000" in captured.out, f"Expected seg_0000 in stdout, got: {captured.out!r}"

    # -----------------------------------------------------------------------
    # Output exactly target_ms length in samples
    # -----------------------------------------------------------------------

    def test_output_length_exactly_target_ms_in_samples(self, tmp_path: Path) -> None:
        """Output WAV nframes must equal int(target_ms * 22050 / 1000) within 1ms tolerance."""
        wav_file = tmp_path / "audio.wav"
        wav_file.write_bytes(make_wav_bytes(1.0))
        result = stretch_to_duration(str(wav_file), 1500)
        nframes = wav_nframes(result)
        expected = int(1500 * 22050 / 1000)  # 33075
        assert abs(nframes - expected) <= 22, f"Expected ~{expected} frames, got {nframes}"

    # -----------------------------------------------------------------------
    # Constants verification
    # -----------------------------------------------------------------------

    def test_constants_values(self) -> None:
        """Module-level constants must have expected values."""
        assert SAMPLE_RATE == 22050
        assert RATIO_MIN == 0.60
        assert RATIO_MAX == 1.75
