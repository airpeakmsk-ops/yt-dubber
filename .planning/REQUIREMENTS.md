# Requirements: YT-Dubber

**Defined:** 2026-03-04
**Core Value:** A Russian speaker can get a synchronized dubbed audio track for any Japanese YouTube video — with a human review step before any audio is generated, ensuring translation quality.

## v1 Requirements

### Extraction

- [ ] **EXTR-01**: User can extract Japanese subtitles from a YouTube URL via yt-dlp
- [ ] **EXTR-02**: Tool handles both manual and auto-generated Japanese subtitles (with VTT rolling-window deduplication)
- [ ] **EXTR-03**: Tool checks for Japanese subtitle availability before download and reports a clear error if none found

### Translation

- [x] **TRAN-01**: Tool translates subtitle text from JP to RU using Claude API (batched, with token-truncation guard)
- [x] **TRAN-02**: Tool exports a DOCX review table: timecode | JP original | RU translation
- [x] **TRAN-03**: Tool reads back user-edited translations from DOCX before proceeding to TTS

### TTS

- [x] **TTS-01**: Tool generates Russian TTS audio per subtitle segment via ElevenLabs (with retry on rate limit)
- [x] **TTS-02**: Segments with no meaningful text (symbols only, < 3 alpha chars) are skipped — silence inserted
- [x] **TTS-03**: Progress is saved after each TTS segment (supports `--resume` on failure)

### Audio

- [ ] **AUDI-01**: Each audio segment is time-stretched/compressed to match original subtitle slot duration
- [ ] **AUDI-02**: Track assembled using absolute timecode positions (no cumulative drift)
- [ ] **AUDI-03**: User receives final dubbed audio track (MP3/WAV) named `<video_id>_dubbed_ru.mp3`

### CLI

- [ ] **CLI-01**: Two-command CLI: `yt-dubber translate <url>` (Phase 1) and `yt-dubber dub <docx>` (Phase 2)
- [ ] **CLI-02**: Claude Code slash command `/translate-video` orchestrates the full pipeline end-to-end

## v2 Requirements

### Video

- **VID-01**: User can mux dubbed audio with original video (MP4 output)

### Languages

- **LANG-01**: Support languages other than JP→RU (configurable source/target)

### Quality

- **QUAL-01**: Real-time streaming translation mode

## Out of Scope

| Feature | Reason |
|---------|--------|
| GUI | CLI-first; GUI deferred indefinitely |
| Real-time streaming | Complexity too high for v1 |
| Video muxing | Audio-only output in v1 |
| Languages other than JP→RU | Extend after v1 validated |
| Automatic TTS without review | User must approve DOCX before TTS |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| EXTR-01 | Phase 2 | Pending |
| EXTR-02 | Phase 2 | Pending |
| EXTR-03 | Phase 2 | Pending |
| TRAN-01 | Phase 3 | Complete |
| TRAN-02 | Phase 3 | Complete |
| TRAN-03 | Phase 3 | Complete |
| TTS-01 | Phase 4 | Complete |
| TTS-02 | Phase 4 | Complete |
| TTS-03 | Phase 4 | Complete |
| AUDI-01 | Phase 5 | Pending |
| AUDI-02 | Phase 5 | Pending |
| AUDI-03 | Phase 5 | Pending |
| CLI-01 | Phase 6 | Pending |
| CLI-02 | Phase 6 | Pending |

**Coverage:**
- v1 requirements: 14 total
- Mapped to phases: 14
- Unmapped: 0

**Note:** Phase 1 (Scaffold) is infrastructure — it has no dedicated v1 requirements but is the
dependency foundation for all other phases. All 14 requirements map to Phases 2-6.

---
*Requirements defined: 2026-03-04*
*Last updated: 2026-03-04 — traceability updated to match ROADMAP.md (Phases 2-6)*
