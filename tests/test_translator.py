from __future__ import annotations
import pytest
from unittest.mock import MagicMock, patch
import anthropic

from yt_dubber.models import SubtitleSegment, SegmentStatus
from yt_dubber.translator import translate_segments


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_segment(index: int, jp_text: str, status: SegmentStatus = SegmentStatus.PENDING) -> SubtitleSegment:
    return SubtitleSegment(
        index=index,
        start_sec=float(index),
        end_sec=float(index) + 1.0,
        duration_sec=1.0,
        jp_text=jp_text,
        status=status,
    )


def make_mock_response(json_text: str, stop_reason: str = "end_turn") -> MagicMock:
    mock = MagicMock()
    mock.content = [MagicMock(text=json_text)]
    mock.stop_reason = stop_reason
    mock.usage.input_tokens = 100
    mock.usage.output_tokens = 50
    return mock


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSymbolOnly:
    def test_symbol_only_skipped(self):
        """Segment with only symbols (< 3 alpha chars) → SKIPPED, no API call."""
        seg = make_segment(1, "♪")
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            result = translate_segments([seg])
        assert result[0].status == SegmentStatus.SKIPPED
        assert result[0].ru_text == ""
        mock_client.messages.create.assert_not_called()

    def test_symbol_only_three_alpha_not_skipped(self):
        """Segment with exactly 3 alpha chars → NOT skipped, sent to API."""
        seg = make_segment(1, "abc")
        response_json = '[{"index": 1, "ru": "абв"}]'
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = make_mock_response(response_json)
            result = translate_segments([seg])
        mock_client.messages.create.assert_called_once()
        assert result[0].status == SegmentStatus.TRANSLATED


class TestHappyPath:
    def test_happy_path_two_segments(self):
        """2 PENDING segments → both translated correctly."""
        segs = [
            make_segment(1, "テスト一"),
            make_segment(2, "テスト二"),
        ]
        response_json = '[{"index": 1, "ru": "Тест1"}, {"index": 2, "ru": "Тест2"}]'
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = make_mock_response(response_json)
            result = translate_segments(segs)
        assert result[0].status == SegmentStatus.TRANSLATED
        assert result[0].ru_text == "Тест1"
        assert result[1].status == SegmentStatus.TRANSLATED
        assert result[1].ru_text == "Тест2"


class TestResume:
    def test_resume_skips_translated(self):
        """Segment already TRANSLATED → not re-sent to API on second call."""
        seg = make_segment(1, "テスト")
        seg.status = SegmentStatus.TRANSLATED
        seg.ru_text = "Уже переведено"
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            result = translate_segments([seg])
        mock_client.messages.create.assert_not_called()
        assert result[0].ru_text == "Уже переведено"

    def test_resume_skips_skipped(self):
        """Segment already SKIPPED → not re-sent to API."""
        seg = make_segment(1, "♪")
        seg.status = SegmentStatus.SKIPPED
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            result = translate_segments([seg])
        mock_client.messages.create.assert_not_called()
        assert result[0].status == SegmentStatus.SKIPPED


class TestMarkdownWrappedJson:
    def test_markdown_wrapped_json_parsed_correctly(self):
        """Mock returns ```json fence → parsed correctly."""
        seg = make_segment(1, "テスト")
        fenced = '```json\n[{"index": 1, "ru": "Тест"}]\n```'
        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.return_value = make_mock_response(fenced)
            result = translate_segments([seg])
        assert result[0].status == SegmentStatus.TRANSLATED
        assert result[0].ru_text == "Тест"


class TestCountMismatch:
    def test_count_mismatch_triggers_retry_then_fallback(self):
        """Mock returns 1 entry for 2-segment batch → retry → per-segment fallback → TRANSLATED."""
        segs = [
            make_segment(1, "テスト一"),
            make_segment(2, "テスト二"),
        ]
        # First two calls return only 1 entry (batch + retry), subsequent calls return 1 entry each
        single_entry_1 = '[{"index": 1, "ru": "Тест1"}]'
        single_entry_2 = '[{"index": 2, "ru": "Тест2"}]'

        call_responses = [
            make_mock_response(single_entry_1),  # batch call — mismatch
            make_mock_response(single_entry_1),  # retry — still mismatch → triggers per-segment
            make_mock_response(single_entry_1),  # per-segment call for seg 1
            make_mock_response(single_entry_2),  # per-segment call for seg 2
        ]

        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = call_responses
            result = translate_segments(segs)

        assert result[0].status == SegmentStatus.TRANSLATED
        assert result[0].ru_text == "Тест1"
        assert result[1].status == SegmentStatus.TRANSLATED
        assert result[1].ru_text == "Тест2"


class TestMaxTokensTruncation:
    def test_max_tokens_triggers_per_segment_fallback(self):
        """stop_reason='max_tokens' → batch treated as failed, fallback to per-segment."""
        segs = [
            make_segment(1, "テスト一"),
            make_segment(2, "テスト二"),
        ]
        truncated = make_mock_response('[{"index": 1, "ru": "Тест1"}]', stop_reason="max_tokens")
        per_seg_1 = make_mock_response('[{"index": 1, "ru": "Тест1"}]')
        per_seg_2 = make_mock_response('[{"index": 2, "ru": "Тест2"}]')

        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [truncated, per_seg_1, per_seg_2]
            result = translate_segments(segs)

        assert result[0].status == SegmentStatus.TRANSLATED
        assert result[1].status == SegmentStatus.TRANSLATED


class TestApiErrorBackoff:
    def test_api_error_backoff_succeeds_on_third(self):
        """APIConnectionError raised twice, succeeds third → result is TRANSLATED."""
        seg = make_segment(1, "テスト")
        response_json = '[{"index": 1, "ru": "Тест"}]'

        conn_error = anthropic.APIConnectionError(request=MagicMock())

        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = [
                conn_error,
                conn_error,
                make_mock_response(response_json),
            ]
            with patch("yt_dubber.translator.time.sleep"):
                result = translate_segments([seg])

        assert result[0].status == SegmentStatus.TRANSLATED
        assert result[0].ru_text == "Тест"

    def test_all_retries_exhausted_marks_error(self):
        """Always raises APIConnectionError → segments marked ERROR."""
        seg = make_segment(1, "テスト")

        conn_error = anthropic.APIConnectionError(request=MagicMock())

        with patch("yt_dubber.translator.anthropic.Anthropic") as mock_cls:
            mock_client = MagicMock()
            mock_cls.return_value = mock_client
            mock_client.messages.create.side_effect = conn_error
            with patch("yt_dubber.translator.time.sleep"):
                result = translate_segments([seg])

        assert result[0].status == SegmentStatus.ERROR
