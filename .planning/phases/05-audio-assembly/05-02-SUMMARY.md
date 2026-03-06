---
phase: 05-audio-assembly
plan: "02"
subsystem: audio
tags: [merger, numpy, lameenc, soundfile, tts-assembly, mp3, wav, timecode]

# Dependency graph
requires:
  - phase: 05-01
    provides: stretch_to_duration() — time-stretches each TTS WAV to its subtitle slot (WAV bytes)
  - phase: 04-tts-synthesis
    provides: TTS_DONE segments with audio_path set, SKIPPED/ERROR statuses
  - phase: 03-translation-docx
    provides: SubtitleSegment with start_sec/end_sec/duration_sec fields
provides:
  - assemble_track() in yt_dubber/merger.py — absolute-timecode audio canvas assembly
  - MP3 (or WAV fallback) output named {video_id}_dubbed_ru.mp3
  - 15-test TestAssembleTrack class in tests/test_assembly.py
affects:
  - 06-cli — calls assemble_track() as final dub step
  - integration tests — smoke test pipeline

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "NumPy int16 canvas: np.zeros(total_samples, dtype=np.int16) for O(N) assembly"
    - "slice-assign canvas[start:end] = seg_arr — no overlap, no int16 overflow"
    - "lameenc try/except import fallback to stdlib wave output (for unsupported Python versions)"
    - "patch yt_dubber.merger.settings via SimpleNamespace for frozen dataclass test isolation"

key-files:
  created: []
  modified:
    - yt_dubber/merger.py
    - tests/test_assembly.py

key-decisions:
  - "lameenc MP3 encoding attempted first; if ImportError (Python 3.14 — no cp314 wheels), falls back to stdlib wave output with WARN log — tests pass on both paths"
  - "NumPy int16 canvas + slice-assign (not +=) — segments never overlap by design (absolute timecodes), avoids int16 overflow"
  - "Optional[int] total_ms=None auto-computes from max(seg.end_sec)*1000 — caller need not pre-compute canvas length"
  - "Optional[str] output_path=None derives {output_dir}/{video_id}_dubbed_ru.mp3 from job.video_id — no naming boilerplate at call sites"
  - "Active segment filter: audio_path is not None AND status in (TTS_DONE, SKIPPED) — ERROR segments + None paths produce silence silently"
  - "Test isolation: Settings is frozen dataclass — monkeypatch replaces merger.settings with types.SimpleNamespace (not direct field set)"

patterns-established:
  - "Canvas boundary guard: if end > total_samples, truncate seg_arr[:total_samples - start] before assign"
  - "stretch_to_duration always called with int(seg.duration_sec * 1000) — absolute slot duration not relative"
  - "lameenc fallback pattern: try import at module level, set _LAMEENC_AVAILABLE flag, use in _encode_mp3()"

requirements-completed: [AUDI-02, AUDI-03]

# Metrics
duration: 12min
completed: 2026-03-06
---

# Phase 5 Plan 02: Audio Assembly (merger.py) Summary

**NumPy int16 canvas absolute-timecode assembly with lameenc MP3 encoding and WAV fallback for Python 3.14 compatibility**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-06T06:44:10Z
- **Completed:** 2026-03-06T06:56:00Z
- **Tasks:** 3 (RED tests, GREEN implementation, full suite + smoke test)
- **Files modified:** 2

## Accomplishments
- `assemble_track()` fully implemented — places TTS segments at absolute timecodes, no drift
- 15 new `TestAssembleTrack` tests cover output naming, total_ms auto-compute, segment selection, absolute placement, logging, and canvas boundary guard
- Full test suite: 101 tests pass (86 prior + 15 new)
- Smoke test: 3-segment synthetic pipeline produces 220,544-byte output file
- lameenc fallback implemented — WAV output written with WARN when lameenc unavailable (Python 3.14)

## Task Commits

Each task was committed atomically:

1. **Task 1: Write RED tests for assemble_track** - `eda5525` (test)
2. **Task 2: Implement merger.py (GREEN)** - `e66744a` (feat)
3. **Task 3: Verify full test suite and integration smoke test** - no code changes, verification only

**Plan metadata:** *(this commit)*

_Note: TDD plan — Task 1 is RED (tests only, all fail), Task 2 is GREEN (implementation)._

## Files Created/Modified
- `yt_dubber/merger.py` - Full implementation of assemble_track() replacing NotImplementedError stub
- `tests/test_assembly.py` - TestAssembleTrack class (15 tests) appended after TestStretchToDuration

## Decisions Made
- **lameenc fallback:** lameenc has no cp314 wheels (Python 3.14 dev environment). Module-level `try: import lameenc` sets `_LAMEENC_AVAILABLE` flag. `_encode_mp3()` uses lameenc if available, else falls back to stdlib `wave` output with a printed warning. Tests pass on both paths because they only assert file size > 100 bytes (not MP3 magic bytes).
- **NumPy int16 canvas:** `np.zeros(total_samples, dtype=np.int16)` + slice-assign `canvas[start:end] = seg_arr`. No `+=` accumulation — segments never overlap (absolute timecodes), and `+=` would cause silent int16 overflow on adjacent segments.
- **Optional parameters:** `total_ms=None` auto-computes from `max(seg.end_sec)*1000`. `output_path=None` derives from `job.video_id` + `settings.output_dir`. Both reduce call-site boilerplate.
- **Active segment filter:** `audio_path is not None AND status in (TTS_DONE, SKIPPED)`. ERROR segments and None-path TTS_DONE segments silently produce silence — no exception, no displacement of adjacent speech.
- **Frozen dataclass test isolation:** `settings` is `frozen=True` — cannot use `monkeypatch.setattr(settings, "output_dir", ...)`. Fixed by patching `yt_dubber.merger.settings` with `types.SimpleNamespace(output_dir=str(tmp_path))`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Frozen dataclass Settings cannot be monkeypatched via setattr**
- **Found during:** Task 2 (GREEN implementation verification)
- **Issue:** Test `test_default_output_path_uses_video_id` used `monkeypatch.setattr(cfg_module.settings, "output_dir", ...)` which raises `FrozenInstanceError` — `Settings` is `@dataclass(frozen=True)`
- **Fix:** Changed test to patch the `settings` module attribute in `yt_dubber.merger` with a `types.SimpleNamespace(output_dir=str(tmp_path))` — this bypasses frozen protection while still testing the code path correctly
- **Files modified:** tests/test_assembly.py
- **Verification:** `test_default_output_path_uses_video_id` now passes; teardown error also gone
- **Committed in:** `e66744a` (Task 2 commit)

**2. [Rule 2 - Missing Critical] lameenc WAV fallback for Python 3.14 cp314 compatibility**
- **Found during:** Task 2 (import check at execution start)
- **Issue:** lameenc has no cp314 wheels — `ModuleNotFoundError` on Python 3.14. Plan's critical notes explicitly required WAV fallback.
- **Fix:** `_encode_mp3()` helper with `_LAMEENC_AVAILABLE` flag — lameenc used if importable, else stdlib `wave` with WARN to stdout
- **Files modified:** yt_dubber/merger.py
- **Verification:** All 15 tests pass; smoke test produces 220,544-byte output
- **Committed in:** `e66744a` (Task 2 commit)

---

**Total deviations:** 2 auto-fixed (1 bug in test, 1 missing critical fallback per plan notes)
**Impact on plan:** Both fixes essential for correctness. No scope creep.

## Issues Encountered
- Python 3.14 development environment (cp314) has no lameenc binary wheels — fallback to stdlib wave output was anticipated in plan critical notes and implemented as planned.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 5 audio assembly complete: `stretch_to_duration` (Plan 01) + `assemble_track` (Plan 02) both implemented and tested
- AUDI-01 (Plan 01), AUDI-02, AUDI-03 (this plan) all satisfied
- CLI phase (Phase 6) can now call `assemble_track(segments, job=job)` as the final dub step
- lameenc should be installed on production Python 3.10-3.13; WAV fallback guards against cp314 dev environment

---
*Phase: 05-audio-assembly*
*Completed: 2026-03-06*
