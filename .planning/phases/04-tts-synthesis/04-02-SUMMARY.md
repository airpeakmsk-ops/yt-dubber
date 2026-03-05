---
phase: 04-tts-synthesis
plan: "02"
subsystem: tts
tags: [elevenlabs, tts, wav, pcm, backoff, retry, checkpoint, resume]

# Dependency graph
requires:
  - phase: 04-01
    provides: checkpoint.save/load + config ElevenLabs settings
provides:
  - should_synthesize predicate (>= 3 alpha chars => True)
  - synthesize_all TTS engine writing seg_XXXX.wav per segment
  - Silence generation for non-speech segments
  - Exponential-backoff retry with Retry-After header support
  - Per-segment checkpoint after every outcome
  - resume=True skips TTS_DONE, retries ERROR
affects: [05-audio-assembly, 06-cli-integration]

# Tech tracking
tech-stack:
  added: [elevenlabs>=1.0.0 (elevenlabs.client.ElevenLabs, VoiceSettings, ApiError)]
  patterns:
    - b"".join(audio_iter) to collect SDK iterator into PCM bytes
    - wave.open(path, "wb") to wrap raw pcm_22050 into valid WAV container
    - BACKOFF_SCHEDULE list drives both retry count and sleep duration
    - Optional job + checkpoint_path params keep synthesize_all backward compatible

key-files:
  created: [tests/test_tts.py]
  modified: [yt_dubber/tts.py]

key-decisions:
  - "synthesize_all extended with optional job + checkpoint_path params (backward compatible) — stub had no path to pass checkpoint"
  - "make_api_error creates real ApiError instances (not MagicMock) — MagicMock(spec=ApiError) cannot be raised by mock side_effect because it does not inherit from BaseException"
  - "BACKOFF_SCHEDULE = [5,10,20,40,80] — 5 entries, each entry is both attempt index and default wait; raise on last attempt after 4 sleeps"
  - "Retry-After from exc.headers.get() wrapped in try/except AttributeError to handle None headers gracefully"

patterns-established:
  - "TTS synthesis pattern: collect iterator -> wrap PCM in WAV container (never write raw bytes as .wav)"
  - "Silence pattern: int(22050 * duration_sec) * 2 zero bytes wrapped in wave.open WAV container"
  - "Retry pattern: enumerate(BACKOFF_SCHEDULE), raise on last index, time.sleep(wait) on earlier indices"

requirements-completed: [TTS-01, TTS-02, TTS-03]

# Metrics
duration: 5min
completed: 2026-03-05
---

# Phase 4 Plan 02: TTS Synthesis Engine Summary

**ElevenLabs TTS engine with should_synthesize predicate, silence generation, exponential-backoff retry with Retry-After header, per-segment WAV output, and checkpoint-based resume**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-03-05T21:06:41Z
- **Completed:** 2026-03-05T21:11:05Z
- **Tasks:** 2 (TDD: RED + GREEN)
- **Files modified:** 2

## Accomplishments

- `should_synthesize(text)` returns True for >= 3 alpha chars, False for symbols/digits/empty
- `synthesize_all()` produces a `seg_XXXX.wav` for each segment in `output_dir/segments/`
- Silence clips (valid WAV, matching duration) written for non-speech segments (status=SKIPPED)
- `_call_with_retry` handles 429 with exponential backoff [5,10,20,40,80]s; honours Retry-After header
- Job continues after 5 exhausted retries (segment.status=ERROR, no exception propagated)
- `checkpoint.save()` invoked after every segment regardless of outcome
- `resume=True` skips TTS_DONE segments and retries ERROR segments
- 30/30 TTS tests GREEN, 61/61 full suite GREEN (zero regressions)

## Task Commits

Each task was committed atomically:

1. **Task 1: RED — Write failing tests for tts.py** - `77c9d12` (test)
2. **Task 2: GREEN — Implement tts.py** - `4a73488` (feat)

_Note: TDD tasks have test commit then feat commit; test file updated in feat commit (make_api_error fix)_

## Files Created/Modified

- `yt_dubber/tts.py` — Full TTS engine replacing NotImplementedError stubs (117 lines)
- `tests/test_tts.py` — 30-test TDD suite across 8 classes covering all plan truths (396 lines)

## Decisions Made

- Extended `synthesize_all` signature with optional `job` and `checkpoint_path` keyword args; the stub had no way to call `checkpoint.save()` without them, but adding them as optional keeps all existing callers unbroken
- `BACKOFF_SCHEDULE = [5, 10, 20, 40, 80]` — 5 entries map directly to max attempts; raise on the 5th attempt after 4 sleeps
- Retry-After header access wrapped in `try/except AttributeError` to handle SDK versions where `exc.headers` may be None or absent

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed make_api_error to return real ApiError instead of MagicMock**
- **Found during:** Task 2 (GREEN — running tests after implementation)
- **Issue:** Plan's suggested `MagicMock(spec=ApiError)` cannot be raised via `mock.side_effect` because MagicMock does not inherit from BaseException; Python 3.14 mock raises `TypeError: exceptions must derive from BaseException`
- **Fix:** Replaced MagicMock factory with real `ApiError(status_code=..., headers=...)` instance construction; ApiError is a real Exception subclass
- **Files modified:** `tests/test_tts.py` (make_api_error helper)
- **Verification:** All 30 tests pass GREEN after fix; retry/backoff tests that previously errored now validate correctly
- **Committed in:** `4a73488` (Task 2 feat commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - Bug)
**Impact on plan:** Essential correctness fix in test helper; implementation was correct as written. No scope creep.

## Issues Encountered

- ElevenLabs package not installed initially (elevenlabs module not found); installed via pip — Rule 3 blocking issue, resolved before RED commit

## Open Question Resolution

- **RESEARCH.md Question 1 (ApiError.headers surface):** `ApiError.headers` is a direct public attribute set in `__init__`. Accessing via `exc.headers.get("Retry-After")` works correctly. Wrapped in `try/except AttributeError` as a defensive measure for future SDK compatibility. The `make_api_error` fix confirmed that real ApiError instances are required (MagicMock won't work).

## Next Phase Readiness

- Phase 5 (Audio Assembly) can begin: `synthesize_all()` produces valid `seg_XXXX.wav` files with correct WAV params (mono, 22050 Hz, 16-bit)
- Checkpoint layer from Plan 01 is fully integrated and tested
- Resume support is verified: TTS_DONE skipped, ERROR retried
- Blocker note: Phase 5 (pyrubberband on Windows) still requires attention — `rubberband.exe` binary needed or librosa fallback

## Self-Check: PASSED

- yt_dubber/tts.py: FOUND
- tests/test_tts.py: FOUND
- .planning/phases/04-tts-synthesis/04-02-SUMMARY.md: FOUND
- Commit 77c9d12 (RED tests): FOUND
- Commit 4a73488 (GREEN implementation): FOUND

---
*Phase: 04-tts-synthesis*
*Completed: 2026-03-05*
