# Roadmap: YT-Dubber

## Overview

Six phases deliver a working end-to-end YouTube dubbing pipeline. Phase 1 lays the project
scaffold and shared data models that all subsequent phases depend on. Phases 2-5 build each
pipeline stage in execution order: subtitle extraction, translation with DOCX review, TTS
synthesis, and audio assembly. Phase 6 wraps everything into a two-command CLI and a Claude
Code slash command, making the tool usable as a product. The result: a Russian speaker can
run two commands — `yt-dubber translate <url>` then `yt-dubber dub <docx>` — and receive
a synchronized dubbed Russian audio track with a human review gate between the two steps.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Scaffold** - Project structure, config loading, shared data models, and pyproject.toml ✓ 2026-03-05
- [ ] **Phase 2: Subtitle Extraction** - yt-dlp subtitle download with deduplication and availability check
- [ ] **Phase 3: Translation + DOCX** - Claude API translation, DOCX export, and user-edited DOCX read-back
- [x] **Phase 4: TTS Synthesis** - ElevenLabs per-segment synthesis with skip logic and resume support (completed 2026-03-05)
- [ ] **Phase 5: Audio Assembly** - Time-stretching, absolute-position track assembly, and MP3 export
- [ ] **Phase 6: CLI + Slash Command** - Two-command CLI packaging and `/translate-video` Claude Code skill

## Phase Details

### Phase 1: Scaffold
**Goal**: The installable Python package exists with working config, environment loading, and shared data models — every later phase can import from it without circular dependencies
**Depends on**: Nothing (first phase)
**Requirements**: None (infrastructure enabling all v1 requirements)
**Success Criteria** (what must be TRUE):
  1. `pip install -e .` succeeds and `yt-dubber --help` prints usage without error
  2. `.env` file with `ANTHROPIC_API_KEY` and `ELEVENLABS_API_KEY` is loaded by config module at import time
  3. `SubtitleSegment` and `JobState` dataclasses are importable and constructable with correct field defaults
  4. `pyproject.toml` declares all runtime dependencies and the `yt-dubber` entry point
**Plans**: 2 plans

Plans:
- [ ] 01-01-PLAN.md — pyproject.toml, models.py, config.py, .env.example (package foundation)
- [ ] 01-02-PLAN.md — cli.py + 8 stub modules (CLI entry point and phase 2-5 signatures)

### Phase 2: Subtitle Extraction
**Goal**: Users can extract clean, deduplicated Japanese subtitle segments from any YouTube URL via a single function call
**Depends on**: Phase 1
**Requirements**: EXTR-01, EXTR-02, EXTR-03
**Success Criteria** (what must be TRUE):
  1. Running `extractor.download_subtitles(url)` on a video with manual Japanese subs produces a non-empty `.srt` file
  2. Running the same call on a video with only auto-generated captions also succeeds, with VTT rolling-window duplicates removed
  3. Running on a URL with no Japanese subtitles raises a descriptive error message (not a silent failure or Python traceback)
  4. The returned list of `SubtitleSegment` objects has correct `start_sec`, `end_sec`, and `jp_text` values matching the source subtitles
**Plans**: TBD

### Phase 3: Translation + DOCX
**Goal**: Users can translate extracted subtitle segments to Russian via the Claude API, review and edit translations in a Word document, then hand the edited file back to the tool
**Depends on**: Phase 2
**Requirements**: TRAN-01, TRAN-02, TRAN-03
**Success Criteria** (what must be TRUE):
  1. `translator.translate_batch(segments)` returns a Russian translation for every input segment with no missing indices, even for batches exceeding 80 segments
  2. A DOCX file is written with four columns (index, timecode, JP original, RU translation) readable in Microsoft Word
  3. After a user edits the RU column and saves the file, `docx_exporter.read_review_docx(path)` returns the edited text indexed by segment number
  4. Segments containing only symbols or fewer than 3 alphabetic characters receive a placeholder translation rather than an API error
**Plans**: 2 plans

Plans:
- [x] 03-01-PLAN.md — config.py update + translator.py TDD (translate_segments with batch/retry/fallback/resume) ✓ 2026-03-05
- [x] 03-02-PLAN.md — docx_exporter.py TDD (write_review_docx + read_review_docx with grey shading + round-trip) ✓ 2026-03-05

### Phase 4: TTS Synthesis
**Goal**: Users can generate Russian TTS audio for every approved subtitle segment, with graceful handling of symbol-only cues, rate limit retries, and the ability to resume a partial run
**Depends on**: Phase 3
**Requirements**: TTS-01, TTS-02, TTS-03
**Success Criteria** (what must be TRUE):
  1. `tts.synthesize_all(segments, voice_id)` produces a `.wav` file for each segment containing meaningful Russian text
  2. Segments where `should_synthesize()` returns False (symbol-only or fewer than 3 alpha chars) produce silence clips instead of API calls
  3. After interrupting synthesis mid-run, re-running with `--resume` skips all segments already marked `tts_done` and completes only the remaining ones
  4. A 429 rate-limit response from ElevenLabs triggers exponential-backoff retry; the run does not abort on a single rate-limit hit
**Plans**: 2 plans

Plans:
- [x] 04-01-PLAN.md — config.py update (3 new ElevenLabs fields) + checkpoint.py TDD (save/load with StrEnum reconstruction) ✓ 2026-03-05
- [ ] 04-02-PLAN.md — tts.py TDD (should_synthesize + synthesize_all with retry, silence, resume, checkpointing)

### Phase 5: Audio Assembly
**Goal**: Users receive a single merged dubbed audio track where each Russian TTS segment is time-stretched to its original subtitle slot and placed at the correct absolute timecode position
**Depends on**: Phase 4
**Requirements**: AUDI-01, AUDI-02, AUDI-03
**Success Criteria** (what must be TRUE):
  1. Each segment's stretched duration equals the original subtitle slot duration (within 50ms tolerance), clamped to 0.60x-1.75x stretch ratio
  2. The final MP3 track is named `<video_id>_dubbed_ru.mp3` and plays at the correct total length matching the source video's subtitle span
  3. Speech in the final track does not drift ahead of or behind the corresponding original video timestamp — verified by spot-checking start time of segment 1, 50, and the last segment
  4. Segments that failed TTS synthesis produce silence at the correct timecode rather than displacing adjacent speech
**Plans**: 2 plans

Plans:
- [ ] 05-01-PLAN.md — pyproject.toml update (lameenc) + audio_sync.py TDD (stretch_to_duration with ratio clamp, silence pad, pyrubberband fallback)
- [ ] 05-02-PLAN.md — merger.py TDD (assemble_track with numpy canvas, absolute timecodes, lameenc MP3 output)

### Phase 6: CLI + Slash Command
**Goal**: Users can run the full pipeline through two named CLI subcommands and through a `/translate-video` Claude Code slash command that orchestrates both steps end-to-end
**Depends on**: Phase 5
**Requirements**: CLI-01, CLI-02
**Success Criteria** (what must be TRUE):
  1. `yt-dubber translate <url>` runs Phase 1 of the pipeline (extraction + translation + DOCX export) and exits with a clear message pointing to the output DOCX
  2. `yt-dubber dub <docx>` runs Phase 2 of the pipeline (DOCX read-back + TTS + assembly) and exits with a clear message pointing to the output MP3
  3. The `/translate-video` Claude Code slash command accepts a YouTube URL, calls `yt-dubber translate`, waits for the user to review the DOCX, then calls `yt-dubber dub` — all within one Claude Code session
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Scaffold | 2/2 | ✓ Complete | 2026-03-05 |
| 2. Subtitle Extraction | 0/TBD | Not started | - |
| 3. Translation + DOCX | 2/2 | ✓ Complete | 2026-03-05 |
| 4. TTS Synthesis | 2/2 | Complete   | 2026-03-05 |
| 5. Audio Assembly | 0/2 | Not started | - |
| 6. CLI + Slash Command | 0/TBD | Not started | - |
