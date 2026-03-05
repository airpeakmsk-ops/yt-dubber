from __future__ import annotations
import json
import re
import time
from typing import List

import anthropic

from yt_dubber.models import SubtitleSegment, SegmentStatus
from yt_dubber.config import settings


class _TruncatedError(Exception):
    """Raised when Claude returns stop_reason='max_tokens' (response cut off)."""


SYSTEM_PROMPT = (
    "You are translating Japanese fishing content (area fishing / area trout) "
    "for a Russian-speaking audience. Use natural, lively commentator-style Russian "
    "with correct fishing terminology and slang (платная рыбалка, форелевые водоёмы, приманки). "
    "Keep lure brand names in their original Latin/romaji form (e.g., Jackall, Timon, Bream Spark). "
    "Translations must be complete phrases — not cut off — but must not expand beyond the original meaning. "
    'Return ONLY a JSON array in the format [{"index": N, "ru": "..."}], one entry per input segment. '
    "No other text, no markdown, no explanation."
)

_RESUME_STATUSES = {
    SegmentStatus.TRANSLATED,
    SegmentStatus.SKIPPED,
    SegmentStatus.APPROVED,
    SegmentStatus.TTS_DONE,
}


def _is_symbol_only(text: str) -> bool:
    """Return True if the text has fewer than 3 alphabetic characters."""
    return sum(1 for c in text if c.isalpha()) < 3


def _build_prompt(batch: list[SubtitleSegment], context: list[SubtitleSegment]) -> str:
    """Build the user-facing translation prompt with optional context segments."""
    lines: list[str] = []
    if context:
        lines.append("# Context (do not translate, reference only)")
        for s in context:
            lines.append(f"[{s.index}] {s.jp_text}")
        lines.append("")
    lines.append("# Translate these segments to Russian:")
    lines.append('Return ONLY a JSON array: [{"index": N, "ru": "..."}]')
    lines.append("One entry per segment. No extra text.")
    for s in batch:
        lines.append(f"[{s.index}] {s.jp_text}")
    return "\n".join(lines)


def _extract_json(text: str) -> list[dict]:
    """
    Three-stage JSON extraction:
    1. Direct json.loads()
    2. Strip markdown code fence (```json ... ```)
    3. Bracket search fallback — find first '[' and last ']'
    Raises ValueError if all stages fail.
    """
    # Stage 1: direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 2: strip markdown fence
    stripped = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    stripped = re.sub(r"\s*```$", "", stripped.strip())
    try:
        return json.loads(stripped)
    except (json.JSONDecodeError, ValueError):
        pass

    # Stage 3: bracket search
    start = text.find("[")
    end = text.rfind("]")
    if start != -1 and end != -1 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except (json.JSONDecodeError, ValueError):
            pass

    raise ValueError(f"Failed to extract JSON from response: {text[:200]!r}")


def _call_claude(
    client: anthropic.Anthropic,
    model: str,
    prompt: str,
    max_retries: int = 3,
) -> list[dict]:
    """
    Call the Claude API with exponential backoff retry logic.
    Raises anthropic.APIConnectionError / anthropic.APIError after max_retries exhausted.
    Raises ValueError on max_tokens truncation.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries):
        try:
            msg = client.messages.create(
                model=model,
                max_tokens=2048,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            if msg.stop_reason == "max_tokens":
                raise _TruncatedError("Response truncated (max_tokens)")
            return _extract_json(msg.content[0].text)
        except (anthropic.APIError, anthropic.APIConnectionError) as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise
    raise last_exc  # type: ignore[misc]  — unreachable but satisfies type checkers


def _translate_single(
    client: anthropic.Anthropic,
    model: str,
    seg: SubtitleSegment,
) -> None:
    """Translate a single segment as a per-segment fallback."""
    prompt = _build_prompt([seg], [])
    try:
        results = _call_claude(client, model, prompt)
        if results and results[0].get("index") == seg.index:
            seg.ru_text = results[0]["ru"]
            seg.status = SegmentStatus.TRANSLATED
        else:
            seg.status = SegmentStatus.ERROR
            seg.error_message = "Per-segment fallback: wrong index in response"
    except Exception as exc:
        seg.status = SegmentStatus.ERROR
        seg.error_message = str(exc)


def _translate_batch(
    client: anthropic.Anthropic,
    model: str,
    batch: list[SubtitleSegment],
    context: list[SubtitleSegment],
) -> None:
    """
    Translate a batch of segments. On count mismatch: retry once, then per-segment fallback.
    On API exception: mark all segments in batch as ERROR.
    """
    prompt = _build_prompt(batch, context)
    try:
        results = _call_claude(client, model, prompt)
        result_map = {r["index"]: r["ru"] for r in results}
        if len(result_map) != len(batch):
            # Retry once
            results = _call_claude(client, model, prompt)
            result_map = {r["index"]: r["ru"] for r in results}
            if len(result_map) != len(batch):
                # Per-segment fallback
                for seg in batch:
                    _translate_single(client, model, seg)
                return
        for seg in batch:
            if seg.index in result_map:
                seg.ru_text = result_map[seg.index]
                seg.status = SegmentStatus.TRANSLATED
            else:
                seg.status = SegmentStatus.ERROR
                seg.error_message = "Index missing from batch response"
    except _TruncatedError:
        # max_tokens: batch response was cut off — fall back to per-segment calls
        for seg in batch:
            _translate_single(client, model, seg)
    except Exception as exc:
        for seg in batch:
            seg.status = SegmentStatus.ERROR
            seg.error_message = str(exc)


def translate_segments(
    segments: List[SubtitleSegment],
    batch_size: int = 20,
    model: str | None = None,
) -> List[SubtitleSegment]:
    """Translate jp_text to ru_text for each segment using the Claude API.

    Processes in batches of batch_size. Updates segment.ru_text and
    segment.status = SegmentStatus.TRANSLATED in-place. Returns the updated list.

    Features:
    - Symbol-only segments (< 3 alpha chars) are SKIPPED without API calls
    - Segments already TRANSLATED / SKIPPED / APPROVED / TTS_DONE are skipped (resume support)
    - Count mismatch triggers one retry, then per-segment fallback
    - API errors trigger exponential backoff (1s, 2s, 4s) with max 3 retries
    - max_tokens guard: treats truncated responses as failed, falls back to per-segment
    """
    model = model or settings.claude_model
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    # Mark symbol-only PENDING/ERROR segments as SKIPPED first
    for seg in segments:
        if seg.status not in _RESUME_STATUSES and _is_symbol_only(seg.jp_text):
            seg.status = SegmentStatus.SKIPPED
            seg.ru_text = ""

    # Collect segments that still need processing
    to_process = [s for s in segments if s.status not in _RESUME_STATUSES]

    # Process in batches
    for i in range(0, len(to_process), batch_size):
        batch = to_process[i : i + batch_size]
        # Build context: up to 2 preceding segments that are already in a resume status
        batch_start_idx = batch[0].index
        context_segs = [
            s for s in segments
            if s.index < batch_start_idx and s.status in _RESUME_STATUSES
        ][-2:]
        _translate_batch(client, model, batch, context_segs)

    return segments
