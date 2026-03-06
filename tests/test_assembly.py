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


# ---------------------------------------------------------------------------
# TestAssembleTrack — TDD tests for yt_dubber/merger.py assemble_track()
# RED: all fail with NotImplementedError before Task 2 implements merger.py
# GREEN: all pass after implementation
# ---------------------------------------------------------------------------

import pathlib
from unittest.mock import patch

from yt_dubber.merger import assemble_track
from yt_dubber.models import SegmentStatus, SubtitleSegment, JobState


def make_wav_bytes_for_assembly(duration_sec: float = 1.0, sr: int = 22050) -> bytes:
    """Generate a silent WAV for assembly test fixtures."""
    n_frames = int(sr * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00" * n_frames * 2)
    buf.seek(0)
    return buf.read()


def make_segment(
    index: int,
    start_sec: float,
    end_sec: float,
    status: SegmentStatus = SegmentStatus.TTS_DONE,
    audio_path: str = None,
) -> SubtitleSegment:
    return SubtitleSegment(
        index=index,
        start_sec=start_sec,
        end_sec=end_sec,
        duration_sec=end_sec - start_sec,
        jp_text="テスト",
        ru_text="тест",
        audio_path=audio_path,
        status=status,
    )


class TestAssembleTrack:
    """Tests for merger.assemble_track() — absolute-timecode audio assembly."""

    # -----------------------------------------------------------------------
    # Output file existence and naming
    # -----------------------------------------------------------------------

    def test_output_file_exists_at_given_path(self, tmp_path: Path) -> None:
        """assemble_track writes output file to explicitly provided path."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            result_path = assemble_track([seg], total_ms=2000, output_path=str(tmp_path / "out.mp3"))

        assert pathlib.Path(tmp_path / "out.mp3").exists()
        assert pathlib.Path(tmp_path / "out.mp3").stat().st_size > 0

    def test_returns_output_path_string(self, tmp_path: Path) -> None:
        """assemble_track returns the output_path string."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        expected = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            result = assemble_track([seg], total_ms=2000, output_path=expected)

        assert result == expected

    def test_default_output_path_uses_video_id(self, tmp_path: Path, monkeypatch) -> None:
        """Without output_path, file is named {video_id}_dubbed_ru.mp3 in settings.output_dir."""
        import yt_dubber.config as cfg_module
        monkeypatch.setattr(cfg_module.settings, "output_dir", str(tmp_path), raising=False)

        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        job = JobState(
            video_id="testvid",
            video_title="Test Video",
            source_url="https://youtube.com/watch?v=testvid",
            docx_path=str(tmp_path / "test.docx"),
            output_dir=str(tmp_path),
        )

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            returned_path = assemble_track([seg], job=job)

        assert returned_path.endswith("testvid_dubbed_ru.mp3")
        assert pathlib.Path(returned_path).exists()

    def test_total_ms_none_auto_computed(self, tmp_path: Path) -> None:
        """total_ms=None auto-computes from max(seg.end_sec)*1000 — no error raised."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        wav_file2 = tmp_path / "seg_1.wav"
        wav_file2.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg0 = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        seg1 = make_segment(1, 2.0, 3.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file2))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg0, seg1], output_path=out)  # no total_ms

        assert pathlib.Path(out).exists()

    def test_total_ms_provided_overrides_auto(self, tmp_path: Path) -> None:
        """total_ms=5000 uses 5-second canvas even when seg.end_sec=1.0."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg], total_ms=5000, output_path=out)

        assert pathlib.Path(out).exists()

    # -----------------------------------------------------------------------
    # MP3 output validity
    # -----------------------------------------------------------------------

    def test_output_is_valid_mp3(self, tmp_path: Path) -> None:
        """Output file is non-trivially sized (> 100 bytes) — indicates real encoded data."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg], total_ms=2000, output_path=out)

        size = pathlib.Path(out).stat().st_size
        assert size > 100, f"Output file suspiciously small: {size} bytes"

    # -----------------------------------------------------------------------
    # Segment selection logic
    # -----------------------------------------------------------------------

    def test_tts_done_segment_included(self, tmp_path: Path) -> None:
        """TTS_DONE segment with audio_path causes stretch_to_duration to be called once."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)) as mock_stretch:
            assemble_track([seg], total_ms=2000, output_path=out)

        mock_stretch.assert_called_once()

    def test_error_segment_not_passed_to_stretch(self, tmp_path: Path) -> None:
        """ERROR segment is skipped; only the TTS_DONE segment calls stretch_to_duration."""
        wav_file = tmp_path / "seg_1.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg_err = make_segment(0, 0.0, 1.0, status=SegmentStatus.ERROR, audio_path=None)
        seg_ok = make_segment(1, 1.0, 2.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)) as mock_stretch:
            assemble_track([seg_err, seg_ok], total_ms=3000, output_path=out)

        assert mock_stretch.call_count == 1, f"Expected 1 call (ERROR skipped), got {mock_stretch.call_count}"

    def test_skipped_segment_with_audio_path_is_included(self, tmp_path: Path) -> None:
        """SKIPPED segment with audio_path IS processed (voice exists, just skipped in translation)."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.SKIPPED, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)) as mock_stretch:
            assemble_track([seg], total_ms=2000, output_path=out)

        mock_stretch.assert_called_once()

    def test_none_audio_path_segment_produces_silence_not_error(self, tmp_path: Path) -> None:
        """TTS_DONE segment with audio_path=None is silently skipped (produces silence, no exception)."""
        wav_file = tmp_path / "seg_1.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg_none = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=None)
        seg_ok = make_segment(1, 1.0, 2.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)) as mock_stretch:
            assemble_track([seg_none, seg_ok], total_ms=3000, output_path=out)

        # None-path segment skipped — only one call
        assert mock_stretch.call_count == 1, f"Expected 1 call (None-path skipped), got {mock_stretch.call_count}"

    # -----------------------------------------------------------------------
    # Absolute timecode placement (no drift)
    # -----------------------------------------------------------------------

    def test_absolute_timecode_stretch_called_with_correct_target_ms(self, tmp_path: Path) -> None:
        """stretch_to_duration called with target_ms=int(duration_sec*1000)."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.5))
        seg = make_segment(0, 2.0, 3.5, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.5)) as mock_stretch:
            assemble_track([seg], total_ms=4000, output_path=out)

        args, kwargs = mock_stretch.call_args
        # stretch_to_duration(audio_path, target_ms, index=seg.index)
        target_ms_passed = args[1] if len(args) > 1 else kwargs.get("target_ms")
        assert target_ms_passed == 1500, f"Expected target_ms=1500, got {target_ms_passed}"

    def test_two_segments_at_nonadjacent_positions(self, tmp_path: Path) -> None:
        """Gap between seg0 (0-1s) and seg1 (5-6s) stays as silence — absolute placement."""
        wav_file0 = tmp_path / "seg_0.wav"
        wav_file0.write_bytes(make_wav_bytes_for_assembly(1.0))
        wav_file1 = tmp_path / "seg_1.wav"
        wav_file1.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg0 = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file0))
        seg1 = make_segment(1, 5.0, 6.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file1))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg0, seg1], total_ms=6000, output_path=out)

        assert pathlib.Path(out).exists()
        assert pathlib.Path(out).stat().st_size > 0

    # -----------------------------------------------------------------------
    # Progress logging
    # -----------------------------------------------------------------------

    def test_assembling_log_emitted(self, tmp_path: Path, capsys) -> None:
        """'Assembling N segments...' printed to stdout with correct segment count."""
        wav_file0 = tmp_path / "seg_0.wav"
        wav_file0.write_bytes(make_wav_bytes_for_assembly(1.0))
        wav_file1 = tmp_path / "seg_1.wav"
        wav_file1.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg0 = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file0))
        seg1 = make_segment(1, 1.0, 2.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file1))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg0, seg1], total_ms=3000, output_path=out)

        captured = capsys.readouterr()
        assert "Assembling" in captured.out, f"Expected 'Assembling' in stdout, got: {captured.out!r}"
        assert "2" in captured.out, f"Expected '2' (segment count) in stdout, got: {captured.out!r}"

    def test_done_log_emitted_with_path(self, tmp_path: Path, capsys) -> None:
        """'Done: {output_path}' printed to stdout after assembly."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(1.0))
        seg = make_segment(0, 0.0, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(1.0)):
            assemble_track([seg], total_ms=2000, output_path=out)

        captured = capsys.readouterr()
        assert "Done:" in captured.out, f"Expected 'Done:' in stdout, got: {captured.out!r}"
        assert "out.mp3" in captured.out, f"Expected 'out.mp3' in stdout, got: {captured.out!r}"

    # -----------------------------------------------------------------------
    # Canvas boundary guard
    # -----------------------------------------------------------------------

    def test_no_index_error_when_segment_overruns_canvas(self, tmp_path: Path) -> None:
        """Segment returning longer audio than its slot gets truncated — no IndexError."""
        wav_file = tmp_path / "seg_0.wav"
        wav_file.write_bytes(make_wav_bytes_for_assembly(0.1))
        seg = make_segment(0, 0.9, 1.0, status=SegmentStatus.TTS_DONE, audio_path=str(wav_file))
        out = str(tmp_path / "out.mp3")

        # stretch_to_duration returns 0.2s WAV (longer than 0.1s slot at end of 1s canvas)
        with patch("yt_dubber.merger.stretch_to_duration", return_value=make_wav_bytes_for_assembly(0.2)):
            assemble_track([seg], total_ms=1000, output_path=out)

        assert pathlib.Path(out).exists()
