from __future__ import annotations

import json
import pathlib

import pytest

from yt_dubber.models import JobState, SubtitleSegment, SegmentStatus
import yt_dubber.checkpoint as checkpoint


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def make_segment(index: int, status: SegmentStatus = SegmentStatus.PENDING) -> SubtitleSegment:
    return SubtitleSegment(
        index=index,
        start_sec=float(index),
        end_sec=float(index) + 1.5,
        duration_sec=1.5,
        jp_text="テスト",
        ru_text="Тест",
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


# ---------------------------------------------------------------------------
# Tests for checkpoint.save()
# ---------------------------------------------------------------------------

def test_save_creates_file(tmp_path: pathlib.Path) -> None:
    """save() must write a file at the given path."""
    path = str(tmp_path / "state.json")
    job = make_job()
    checkpoint.save(job, path)
    assert pathlib.Path(path).exists()


def test_save_produces_valid_json(tmp_path: pathlib.Path) -> None:
    """save() output must be parseable by json.loads."""
    path = str(tmp_path / "state.json")
    job = make_job([make_segment(0)])
    checkpoint.save(job, path)
    content = pathlib.Path(path).read_text(encoding="utf-8")
    parsed = json.loads(content)
    assert isinstance(parsed, dict)


def test_save_overwrites_existing_file(tmp_path: pathlib.Path) -> None:
    """save() over an existing file must overwrite it (idempotent)."""
    path = str(tmp_path / "state.json")
    # Write once
    job1 = make_job()
    checkpoint.save(job1, path)
    # Write again with different data
    job2 = make_job([make_segment(0)])
    checkpoint.save(job2, path)
    content = pathlib.Path(path).read_text(encoding="utf-8")
    parsed = json.loads(content)
    # Second write should have segments
    assert len(parsed["segments"]) == 1


# ---------------------------------------------------------------------------
# Tests for checkpoint.load()
# ---------------------------------------------------------------------------

def test_load_returns_jobstate_instance(tmp_path: pathlib.Path) -> None:
    """load() must return a JobState instance, not a plain dict."""
    path = str(tmp_path / "state.json")
    job = make_job()
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    assert isinstance(result, JobState)


def test_load_reconstructs_segments_as_subtitle_segment_objects(tmp_path: pathlib.Path) -> None:
    """load() must reconstruct segments as SubtitleSegment objects, not plain dicts."""
    path = str(tmp_path / "state.json")
    job = make_job([make_segment(0)])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    assert len(result.segments) == 1
    seg = result.segments[0]
    assert isinstance(seg, SubtitleSegment)


def test_load_segment_status_is_enum_not_str(tmp_path: pathlib.Path) -> None:
    """load() must reconstruct SegmentStatus as an enum, not a plain string."""
    path = str(tmp_path / "state.json")
    job = make_job([make_segment(0, status=SegmentStatus.PENDING)])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    seg = result.segments[0]
    assert isinstance(seg.status, SegmentStatus)
    assert not isinstance(seg.status, str) or type(seg.status) is SegmentStatus


def test_roundtrip_tts_done_status(tmp_path: pathlib.Path) -> None:
    """SegmentStatus.TTS_DONE must survive save→load roundtrip as SegmentStatus.TTS_DONE."""
    path = str(tmp_path / "state.json")
    job = make_job([make_segment(0, status=SegmentStatus.TTS_DONE)])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    assert result.segments[0].status is SegmentStatus.TTS_DONE


def test_roundtrip_error_status(tmp_path: pathlib.Path) -> None:
    """SegmentStatus.ERROR must survive save→load roundtrip as SegmentStatus.ERROR."""
    path = str(tmp_path / "state.json")
    job = make_job([make_segment(0, status=SegmentStatus.ERROR)])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    assert result.segments[0].status is SegmentStatus.ERROR


def test_roundtrip_optional_fields_none(tmp_path: pathlib.Path) -> None:
    """audio_path=None and error_message=None must survive roundtrip as None."""
    path = str(tmp_path / "state.json")
    seg = SubtitleSegment(
        index=0, start_sec=0.0, end_sec=1.5, duration_sec=1.5,
        jp_text="テスト", ru_text="Тест",
        audio_path=None, error_message=None,
    )
    job = make_job([seg])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    loaded_seg = result.segments[0]
    assert loaded_seg.audio_path is None
    assert loaded_seg.error_message is None


def test_roundtrip_optional_fields_with_values(tmp_path: pathlib.Path) -> None:
    """audio_path and error_message with non-None values must survive roundtrip correctly."""
    path = str(tmp_path / "state.json")
    seg = SubtitleSegment(
        index=0, start_sec=0.0, end_sec=1.5, duration_sec=1.5,
        jp_text="テスト", ru_text="Тест",
        audio_path="/some/path/audio.mp3",
        error_message="something went wrong",
        status=SegmentStatus.ERROR,
    )
    job = make_job([seg])
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    loaded_seg = result.segments[0]
    assert loaded_seg.audio_path == "/some/path/audio.mp3"
    assert loaded_seg.error_message == "something went wrong"


def test_roundtrip_multiple_segments(tmp_path: pathlib.Path) -> None:
    """load() on a file with multiple segments must reconstruct all of them."""
    path = str(tmp_path / "state.json")
    segments = [make_segment(i, status) for i, status in enumerate([
        SegmentStatus.PENDING,
        SegmentStatus.TRANSLATED,
        SegmentStatus.APPROVED,
        SegmentStatus.TTS_DONE,
    ])]
    job = make_job(segments)
    checkpoint.save(job, path)
    result = checkpoint.load(path)
    assert len(result.segments) == 4
    for loaded_seg in result.segments:
        assert isinstance(loaded_seg, SubtitleSegment)
        assert isinstance(loaded_seg.status, SegmentStatus)
