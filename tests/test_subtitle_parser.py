from __future__ import annotations
import pytest
from yt_dubber.subtitle_parser import parse_srt, parse_srt_file
from yt_dubber.models import SubtitleSegment


# ---------------------------------------------------------------------------
# Test 1: Normal SRT — 3 blocks, correct index/times/text
# ---------------------------------------------------------------------------
def test_normal_srt_three_blocks():
    content = (
        "1\n00:00:01,000 --> 00:00:04,000\n日本語\n\n"
        "2\n00:00:05,000 --> 00:00:08,500\nテスト\n\n"
        "3\n00:00:09,000 --> 00:00:11,000\nサンプル\n"
    )
    segs = parse_srt(content)
    assert len(segs) == 3

    s = segs[0]
    assert s.index == 1
    assert s.start_sec == pytest.approx(1.0)
    assert s.end_sec == pytest.approx(4.0)
    assert s.duration_sec == pytest.approx(3.0)
    assert s.jp_text == "日本語"

    assert segs[1].index == 2
    assert segs[1].jp_text == "テスト"
    assert segs[2].jp_text == "サンプル"


# ---------------------------------------------------------------------------
# Test 2: Timecode precision (milliseconds)
# ---------------------------------------------------------------------------
def test_timecode_precision():
    content = "1\n00:01:23,456 --> 00:01:27,890\nテキスト\n"
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].start_sec == pytest.approx(83.456)
    assert segs[0].end_sec == pytest.approx(87.890)


# ---------------------------------------------------------------------------
# Test 3: VTT inline tag stripping
# ---------------------------------------------------------------------------
def test_vtt_tag_stripping():
    content = "1\n00:00:01,000 --> 00:00:03,000\nこんにちは<c.colorCCCCCC><00:00:01.234></c>\n"
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].jp_text == "こんにちは"


# ---------------------------------------------------------------------------
# Test 4: Empty text block (after tag stripping) — silently skipped
# ---------------------------------------------------------------------------
def test_empty_text_block_skipped():
    content = (
        "1\n00:00:01,000 --> 00:00:02,000\n<c></c>\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\n正常\n"
    )
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].jp_text == "正常"


# ---------------------------------------------------------------------------
# Test 5: Multi-line text joined with space
# ---------------------------------------------------------------------------
def test_multiline_text_joined():
    content = "1\n00:00:01,000 --> 00:00:05,000\n第一行\n第二行\n"
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].jp_text == "第一行 第二行"


# ---------------------------------------------------------------------------
# Test 6: parse_srt_file — UTF-8 round-trip
# ---------------------------------------------------------------------------
def test_parse_srt_file_utf8(tmp_path):
    srt_file = tmp_path / "test.srt"
    srt_file.write_text("1\n00:00:01,000 --> 00:00:03,000\n日本語テスト\n", encoding="utf-8")
    segs = parse_srt_file(str(srt_file))
    assert len(segs) == 1
    assert segs[0].jp_text == "日本語テスト"
    assert segs[0].start_sec == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 7: Non-integer first line — block skipped, no exception
# ---------------------------------------------------------------------------
def test_invalid_index_block_skipped():
    content = (
        "A\n00:00:01,000 --> 00:00:02,000\ntext\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\n有効\n"
    )
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].jp_text == "有効"


# ---------------------------------------------------------------------------
# Test 8: Bad timecode format — block skipped, no exception
# ---------------------------------------------------------------------------
def test_bad_timecode_skipped():
    content = (
        "1\nNOT_A_TIMECODE\ntext\n\n"
        "2\n00:00:03,000 --> 00:00:05,000\n有効\n"
    )
    segs = parse_srt(content)
    assert len(segs) == 1
    assert segs[0].jp_text == "有効"
