from __future__ import annotations

import wave
import pathlib
from typing import Iterator
from unittest.mock import MagicMock, patch, call

import pytest

from yt_dubber.models import SubtitleSegment, SegmentStatus, JobState
from elevenlabs.core.api_error import ApiError
from yt_dubber.tts import should_synthesize, synthesize_all


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_segment(
    index: int,
    ru_text: str = "Привет мир",
    status: SegmentStatus = SegmentStatus.PENDING,
    duration_sec: float = 1.0,
) -> SubtitleSegment:
    return SubtitleSegment(
        index=index,
        start_sec=float(index),
        end_sec=float(index) + duration_sec,
        duration_sec=duration_sec,
        jp_text="テスト",
        ru_text=ru_text,
        status=status,
    )


def make_job(segments=None) -> JobState:
    return JobState(
        video_id="abc123",
        video_title="Test",
        source_url="https://yt.be/abc123",
        docx_path="/tmp/review.docx",
        output_dir="/tmp/output",
        segments=segments or [],
    )


def make_api_error(status_code: int = 429, retry_after: str | None = None) -> ApiError:
    """Create a real ApiError instance (must derive from BaseException to be raised)."""
    headers = {"Retry-After": retry_after} if retry_after else {}
    err = ApiError(status_code=status_code, headers=headers)
    return err


def fake_pcm_bytes(n_frames: int = 22050) -> bytes:
    """Return valid S16LE PCM bytes for n_frames at 22050 Hz mono."""
    return b"\x00" * (n_frames * 2)


# ---------------------------------------------------------------------------
# Class TestShouldSynthesize
# ---------------------------------------------------------------------------

class TestShouldSynthesize:
    def test_many_alpha_chars_returns_true(self):
        assert should_synthesize("Привет мир!") is True

    def test_exactly_3_alpha_chars_boundary_returns_true(self):
        assert should_synthesize("abc") is True

    def test_only_2_alpha_chars_returns_false(self):
        assert should_synthesize("ab") is False

    def test_symbol_only_returns_false(self):
        assert should_synthesize("♪") is False

    def test_empty_string_returns_false(self):
        assert should_synthesize("") is False

    def test_punctuation_only_returns_false(self):
        assert should_synthesize("...") is False

    def test_digits_only_returns_false(self):
        assert should_synthesize("12345") is False


# ---------------------------------------------------------------------------
# Class TestSynthesizeAll
# ---------------------------------------------------------------------------

class TestSynthesizeAll:
    def test_happy_path_status_tts_done(self, tmp_path):
        """Happy path: 1 segment with ru_text -> ElevenLabs called -> status = TTS_DONE."""
        seg = make_segment(1)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert result[0].status == SegmentStatus.TTS_DONE

    def test_happy_path_audio_path_correct(self, tmp_path):
        """Happy path: segment.audio_path == '{output_dir}/segments/seg_0001.wav'."""
        seg = make_segment(1)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        expected = str(tmp_path / "segments" / "seg_0001.wav")
        assert result[0].audio_path == expected

    def test_file_naming_zero_padded_index(self, tmp_path):
        """segment.index=42 -> filename = 'seg_0042.wav'."""
        seg = make_segment(42)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        expected = str(tmp_path / "segments" / "seg_0042.wav")
        assert result[0].audio_path == expected

    def test_elevenlabs_called_with_correct_params(self, tmp_path):
        """ElevenLabs called with voice_id, model_id='eleven_multilingual_v2', output_format='pcm_22050'."""
        from elevenlabs import VoiceSettings
        seg = make_segment(1)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            synthesize_all([seg], voice_id="test_voice_id", output_dir=str(tmp_path))
            call_kwargs = mock_client.text_to_speech.convert.call_args
        assert call_kwargs.kwargs.get("voice_id") == "test_voice_id" or call_kwargs.args[1] == "test_voice_id"
        assert call_kwargs.kwargs.get("model_id") == "eleven_multilingual_v2"
        assert call_kwargs.kwargs.get("output_format") == "pcm_22050"

    def test_elevenlabs_called_with_voice_settings(self, tmp_path):
        """ElevenLabs called with VoiceSettings(stability=0.85, similarity_boost=0.80)."""
        from elevenlabs import VoiceSettings
        seg = make_segment(1)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
            call_kwargs = mock_client.text_to_speech.convert.call_args
        vs = call_kwargs.kwargs.get("voice_settings")
        assert vs is not None
        assert vs.stability == 0.85
        assert vs.similarity_boost == 0.80

    def test_written_wav_is_valid(self, tmp_path):
        """Written WAV file is valid: wave.open() succeeds, nchannels=1, sampwidth=2, framerate=22050."""
        seg = make_segment(1)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes(22050)])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        wav_path = result[0].audio_path
        assert wav_path is not None
        with wave.open(wav_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 22050


# ---------------------------------------------------------------------------
# Class TestSilenceGeneration
# ---------------------------------------------------------------------------

class TestSilenceGeneration:
    def test_symbol_only_segment_elevenlabs_not_called(self, tmp_path):
        """Symbol-only segment (should_synthesize=False) -> ElevenLabs NOT called."""
        seg = make_segment(1, ru_text="♪")
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
            mock_client.text_to_speech.convert.assert_not_called()

    def test_silence_file_written_at_correct_path(self, tmp_path):
        """Silence file written at correct path (same seg_XXXX.wav naming)."""
        seg = make_segment(5, ru_text="♪")
        with patch("yt_dubber.tts.ElevenLabs"):
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        expected = str(tmp_path / "segments" / "seg_0005.wav")
        assert result[0].audio_path == expected
        assert pathlib.Path(expected).exists()

    def test_silence_segment_status_is_skipped(self, tmp_path):
        """segment.status = SKIPPED after silence."""
        seg = make_segment(1, ru_text="♪")
        with patch("yt_dubber.tts.ElevenLabs"):
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert result[0].status == SegmentStatus.SKIPPED

    def test_silence_wav_params_valid(self, tmp_path):
        """WAV params: nchannels=1, sampwidth=2, framerate=22050."""
        seg = make_segment(1, ru_text="♪")
        with patch("yt_dubber.tts.ElevenLabs"):
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        with wave.open(result[0].audio_path, "rb") as wf:
            assert wf.getnchannels() == 1
            assert wf.getsampwidth() == 2
            assert wf.getframerate() == 22050

    def test_silence_wav_frame_count_matches_duration(self, tmp_path):
        """WAV frame count == int(22050 * duration_sec) (within 1 frame tolerance)."""
        duration = 2.5
        seg = make_segment(1, ru_text="♪", duration_sec=duration)
        with patch("yt_dubber.tts.ElevenLabs"):
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        expected_frames = int(22050 * duration)
        with wave.open(result[0].audio_path, "rb") as wf:
            actual_frames = wf.getnframes()
        assert abs(actual_frames - expected_frames) <= 1


# ---------------------------------------------------------------------------
# Class TestRetry
# ---------------------------------------------------------------------------

class TestRetry:
    def test_429_on_first_two_attempts_then_success(self, tmp_path):
        """429 ApiError on first 2 attempts, success on 3rd -> TTS_DONE (not ERROR)."""
        seg = make_segment(1)
        err = make_api_error(429)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep"):
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                err, err, iter([fake_pcm_bytes()])
            ]
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert result[0].status == SegmentStatus.TTS_DONE

    def test_time_sleep_called_with_backoff_values(self, tmp_path):
        """time.sleep() called with backoff values 5, 10 (first two waits from schedule)."""
        seg = make_segment(1)
        err = make_api_error(429)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep") as mock_sleep:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                err, err, iter([fake_pcm_bytes()])
            ]
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        sleep_calls = [c.args[0] for c in mock_sleep.call_args_list]
        assert sleep_calls[0] == 5
        assert sleep_calls[1] == 10


# ---------------------------------------------------------------------------
# Class TestRetryAfterHeader
# ---------------------------------------------------------------------------

class TestRetryAfterHeader:
    def test_retry_after_header_overrides_backoff(self, tmp_path):
        """429 with Retry-After: '30' header -> time.sleep called with 30.0."""
        seg = make_segment(1)
        err = make_api_error(429, retry_after="30")
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep") as mock_sleep:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                err, iter([fake_pcm_bytes()])
            ]
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert mock_sleep.call_args_list[0].args[0] == 30.0

    def test_no_retry_after_header_uses_schedule(self, tmp_path):
        """429 without Retry-After header -> time.sleep called with schedule value (5.0)."""
        seg = make_segment(1)
        err = make_api_error(429)  # no retry_after
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep") as mock_sleep:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                err, iter([fake_pcm_bytes()])
            ]
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert mock_sleep.call_args_list[0].args[0] == 5.0

    def test_none_headers_uses_schedule_no_keyerror(self, tmp_path):
        """429 with exc.headers=None -> time.sleep called with schedule value (no KeyError)."""
        seg = make_segment(1)
        err = make_api_error(429)
        err.headers = None  # override to None
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep") as mock_sleep:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                err, iter([fake_pcm_bytes()])
            ]
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert mock_sleep.call_args_list[0].args[0] == 5.0


# ---------------------------------------------------------------------------
# Class TestExhaustedRetry
# ---------------------------------------------------------------------------

class TestExhaustedRetry:
    def test_always_429_after_5_attempts_status_error(self, tmp_path):
        """Always raises 429 -> after 5 attempts: segment.status = ERROR (not raised)."""
        seg = make_segment(1)
        err = make_api_error(429)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep"):
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = err
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path))
        assert result[0].status == SegmentStatus.ERROR

    def test_job_continues_after_first_segment_errors(self, tmp_path):
        """Job continues: second segment (no error) still synthesized after first segment errors."""
        seg1 = make_segment(1)
        seg2 = make_segment(2)
        err = make_api_error(429)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.time.sleep"):
            mock_client = MockClient.return_value
            # seg1 always fails, seg2 succeeds
            mock_client.text_to_speech.convert.side_effect = [
                err, err, err, err, err,  # 5 attempts for seg1
                iter([fake_pcm_bytes()]),  # seg2 success
            ]
            result = synthesize_all([seg1, seg2], voice_id="test_voice", output_dir=str(tmp_path))
        assert result[0].status == SegmentStatus.ERROR
        assert result[1].status == SegmentStatus.TTS_DONE


# ---------------------------------------------------------------------------
# Class TestCheckpointCalledPerSegment
# ---------------------------------------------------------------------------

class TestCheckpointCalledPerSegment:
    def test_checkpoint_called_once_per_segment(self, tmp_path):
        """Mock checkpoint.save() -- assert called once per segment regardless of outcome."""
        seg1 = make_segment(1)
        seg2 = make_segment(2)
        job = make_job([seg1, seg2])
        err = make_api_error(429)
        checkpoint_path = str(tmp_path / "checkpoint.json")
        with patch("yt_dubber.tts.ElevenLabs") as MockClient, \
             patch("yt_dubber.tts.checkpoint.save") as mock_save, \
             patch("yt_dubber.tts.time.sleep"):
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.side_effect = [
                iter([fake_pcm_bytes()]),  # seg1 success
                err, err, err, err, err,   # seg2 always 429 -> ERROR
            ]
            synthesize_all(
                [seg1, seg2], voice_id="test_voice", output_dir=str(tmp_path),
                job=job, checkpoint_path=checkpoint_path,
            )
        assert mock_save.call_count == 2


# ---------------------------------------------------------------------------
# Class TestResume
# ---------------------------------------------------------------------------

class TestResume:
    def test_resume_true_tts_done_skips_elevenlabs(self, tmp_path):
        """resume=True + segment.status=TTS_DONE -> ElevenLabs NOT called for that segment."""
        seg = make_segment(1, status=SegmentStatus.TTS_DONE)
        seg.audio_path = str(tmp_path / "segments" / "seg_0001.wav")
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path), resume=True)
            mock_client.text_to_speech.convert.assert_not_called()

    def test_resume_true_error_status_retries(self, tmp_path):
        """resume=True + segment.status=ERROR -> ElevenLabs IS called (retry)."""
        seg = make_segment(1, status=SegmentStatus.ERROR)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path), resume=True)
            mock_client.text_to_speech.convert.assert_called_once()
        assert result[0].status == SegmentStatus.TTS_DONE

    def test_resume_true_pending_status_synthesizes(self, tmp_path):
        """resume=True + segment.status=PENDING -> ElevenLabs IS called (normal)."""
        seg = make_segment(1, status=SegmentStatus.PENDING)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path), resume=True)
            mock_client.text_to_speech.convert.assert_called_once()
        assert result[0].status == SegmentStatus.TTS_DONE

    def test_resume_false_tts_done_synthesizes_again(self, tmp_path):
        """resume=False + segment.status=TTS_DONE -> ElevenLabs IS called (no skip without resume)."""
        seg = make_segment(1, status=SegmentStatus.TTS_DONE)
        with patch("yt_dubber.tts.ElevenLabs") as MockClient:
            mock_client = MockClient.return_value
            mock_client.text_to_speech.convert.return_value = iter([fake_pcm_bytes()])
            result = synthesize_all([seg], voice_id="test_voice", output_dir=str(tmp_path), resume=False)
            mock_client.text_to_speech.convert.assert_called_once()
        assert result[0].status == SegmentStatus.TTS_DONE
