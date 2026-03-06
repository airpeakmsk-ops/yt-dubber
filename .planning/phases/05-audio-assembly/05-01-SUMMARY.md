---
phase: 05-audio-assembly
plan: 01
subsystem: audio
tags: [librosa, soundfile, numpy, pyrubberband, time-stretch, wav, tdd]

# Dependency graph
requires:
  - phase: 04-tts-synthesis
    provides: Per-segment WAV files (mono, 22050 Hz, PCM_16) output by synthesize_all()
provides:
  - stretch_to_duration(audio_path, target_ms, index) -> WAV bytes of exactly target_ms duration
  - RATIO_MIN=0.60, RATIO_MAX=1.75 clamping with WARN logging
  - _time_stretch() with pyrubberband primary / librosa fallback
  - 17 TDD tests in tests/test_assembly.py (TestStretchToDuration)
affects:
  - 05-02 (merger.py assemble_track — calls stretch_to_duration per segment)
  - 06-cli (end-to-end dubbing pipeline)

# Tech tracking
tech-stack:
  added:
    - soundfile>=0.12.0 (WAV I/O — read float32, write PCM_16)
    - librosa>=0.10.0 (time stretching fallback + resample)
    - lameenc>=1.7.0 (declared in pyproject.toml dependencies; used by merger.py in plan 05-02)
  patterns:
    - TDD RED-GREEN with immediate commit per phase
    - pyrubberband primary / librosa.effects.time_stretch fallback on any Exception
    - Short-segment guard: skip time_stretch when len(y) < 512 samples
    - Trim-or-pad to exact target_samples = int(target_ms * SAMPLE_RATE / 1000)
    - WARN format: f"WARN: seg_{index:04d} clamped (ratio {actual:.2f}x -> {limit:.2f}x)"

key-files:
  created:
    - tests/test_assembly.py
  modified:
    - yt_dubber/audio_sync.py
    - pyproject.toml

key-decisions:
  - "lameenc added to [project.dependencies] (not optional-dependencies) — required runtime dep for merger.py"
  - "librosa primary time-stretch with pyrubberband as optional fast path (try/except any Exception)"
  - "Exact trim+pad to int(target_ms * 22050 / 1000) samples ensures zero-drift audio assembly"
  - "ratio > RATIO_MAX uses 1.00x limit in WARN (native speed branch, no compression)"
  - "ratio < RATIO_MIN uses RATIO_MIN (0.60x) in WARN (maximum compression branch)"
  - "lameenc cannot be pip-installed on Python 3.14 (no cp314 wheels yet) — pyproject.toml entry is correct for production; not needed by audio_sync.py"

patterns-established:
  - "stretch_to_duration always returns exactly int(target_ms * SAMPLE_RATE / 1000) samples as WAV bytes"
  - "All audio output: mono, 22050 Hz, PCM_16LE WAV"
  - "WARN log to stdout (print) — same pattern as tts.py progress logs"

requirements-completed:
  - AUDI-01

# Metrics
duration: 8min
completed: 2026-03-06
---

# Phase 05 Plan 01: Audio Sync (stretch_to_duration) Summary

**stretch_to_duration() implemented using librosa time-stretch with pyrubberband fallback, RATIO_MIN/MAX clamping, exact trim+pad to target_ms, and 17 TDD tests all GREEN**

## Performance

- **Duration:** 8 min
- **Started:** 2026-03-06T06:33:15Z
- **Completed:** 2026-03-06T06:41:32Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- Implemented `stretch_to_duration(audio_path, target_ms, index=0) -> bytes` in `yt_dubber/audio_sync.py`
- Added SAMPLE_RATE=22050, RATIO_MIN=0.60, RATIO_MAX=1.75 as module-level constants
- Clamping logic: ratio > 1.75 = native speed + silence pad + WARN; ratio < 0.60 = 0.60x clamp + silence pad + WARN
- Short-segment guard (< 512 samples) skips time_stretch to avoid librosa FFT minimum errors
- Pyrubberband primary time-stretch with librosa.effects.time_stretch fallback on any Exception
- 17 TDD tests written (RED then GREEN), all pass; full suite: 86/86 tests GREEN

## Task Commits

Each task was committed atomically:

1. **Task 1: Add lameenc to pyproject.toml and write RED tests** - `b5b09d2` (test)
2. **Task 2: Implement audio_sync.py (GREEN)** - `a405c59` (feat)
3. **Task 3: Verify full test suite** - (verification only, no new files)

_Note: Task 3 was verification-only — 86/86 tests pass, no regressions from prior 69 tests._

## Files Created/Modified

- `yt_dubber/audio_sync.py` - Full implementation of stretch_to_duration() replacing NotImplementedError stub
- `tests/test_assembly.py` - 17 TDD tests in TestStretchToDuration class
- `pyproject.toml` - Added lameenc>=1.7.0 to [project.dependencies]

## Decisions Made

- **lameenc in required deps, not optional:** lameenc is a runtime requirement for merger.py (plan 05-02); it belongs in `[project.dependencies]`, not `[project.optional-dependencies]`. Pip install on Python 3.14 fails (no cp314 wheels), but the declaration is correct for production use on Python 3.10-3.13.
- **librosa primary, pyrubberband optional:** pyrubberband requires a native `rubberband.exe` binary (known Windows concern per STATE.md). `_time_stretch()` tries pyrubberband first, catches any Exception, falls back to librosa.
- **Exact trim+pad strategy:** After time-stretch, output is trimmed to exactly `int(target_ms * 22050 / 1000)` samples or zero-padded to that length. This ensures zero-drift absolute-timecode assembly in plan 05-02.
- **WARN limit for ratio > RATIO_MAX is "1.00x":** When TTS is too long for the slot, audio plays at native speed (no stretch). The limit displayed is 1.00x (the effective speed applied).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] soundfile and librosa not installed in Python 3.14 environment**
- **Found during:** Task 2 (running GREEN tests)
- **Issue:** `ModuleNotFoundError: No module named 'soundfile'` — audio_sync.py imports soundfile and librosa at module level
- **Fix:** Ran `pip install soundfile librosa` (both installed successfully for Python 3.14)
- **Files modified:** None (environment-only change)
- **Verification:** All 17 tests pass after installation
- **Committed in:** Part of Task 2 execution (no file change needed)

---

**Total deviations:** 1 auto-fixed (1 blocking dependency install)
**Impact on plan:** Required for tests to run. No scope creep.

## Issues Encountered

- **lameenc not installable on Python 3.14:** lameenc has no cp314 wheels on PyPI (latest wheels are cp313). The pyproject.toml dependency declaration is correct; the package will install on Python 3.10-3.13 (production targets). The audio_sync.py module does not import lameenc (it is only used in merger.py, plan 05-02).

## Next Phase Readiness

- `stretch_to_duration()` is production-ready: handles normal ratios, clamping, mono enforcement, short segments, and pyrubberband/librosa fallback
- Plan 05-02 (merger.py / assemble_track) can call `stretch_to_duration()` per segment as designed
- lameenc declaration in pyproject.toml is ready for production deployment on Python <= 3.13

---
*Phase: 05-audio-assembly*
*Completed: 2026-03-06*

## Self-Check: PASSED

- yt_dubber/audio_sync.py: FOUND
- tests/test_assembly.py: FOUND
- pyproject.toml: FOUND (lameenc>=1.7.0 present)
- 05-01-SUMMARY.md: FOUND
- Commit b5b09d2 (test): FOUND
- Commit a405c59 (feat): FOUND
- 17/17 TestStretchToDuration tests: PASS
