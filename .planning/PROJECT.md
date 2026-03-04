# YT-Dubber

## What This Is

A Python CLI tool that automatically translates and dubs Japanese YouTube videos into Russian.
Given a YouTube URL, it extracts embedded Japanese subtitles, translates them to Russian using
the Claude API, exports a DOCX review table (timecode | original | translation) for human QA,
then synthesizes TTS audio per subtitle segment via ElevenLabs and produces a time-synchronized
dubbed audio track (MP3/WAV) where speech is aligned to original subtitle timecodes.

## Core Value

A Russian speaker can get a synchronized dubbed audio track for any Japanese YouTube video —
with a human review step before any audio is generated, ensuring translation quality.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] Extract embedded Japanese subtitles from a YouTube URL via yt-dlp
- [ ] Translate subtitle text from Japanese to Russian using Claude API
- [ ] Export DOCX review table with 3 columns: timecode | original JP | Russian translation
- [ ] Generate Russian TTS audio per subtitle segment via ElevenLabs API
- [ ] Stretch/compress each audio segment to match original segment duration
- [ ] Preserve inter-sentence pauses using timecodes from original subtitles
- [ ] Output a merged dubbed audio track (MP3/WAV)
- [ ] Claude Code slash command `/translate-video` that orchestrates the Python tool

### Out of Scope

- Real-time streaming translation — complexity too high for v1
- GUI — CLI-first
- Languages other than JP→RU — extend after v1 is validated
- Video muxing — audio-only output in v1, video merge deferred to v2
- Automatic TTS without review — user must approve translation DOCX first

## Context

- Reference project: Auto-Synced-Translated-Dubs (ThioJoe/GitHub) — Python, ElevenLabs + Google Translate
- Tech stack: Python 3.10+, yt-dlp, Claude API (anthropic SDK), ElevenLabs Python SDK, python-docx, FFmpeg, pydub/pyrubberband
- Translation engine: Claude API (sonnet model) — chosen for JP→RU context quality
- TTS engine: ElevenLabs — user specified, neural voice quality
- Subtitle formats: SRT, VTT, ASS (yt-dlp extracts these)
- Output: WAV/MP3 audio track, named `<video_id>_dubbed_ru.mp3`

## Constraints

- **API**: ElevenLabs API key required (paid plan for synthesis quota)
- **API**: `ANTHROPIC_API_KEY` required for translation
- **Tools**: FFmpeg must be installed system-wide
- **Python**: 3.10+ required (match yt-dlp requirements)
- **Review gate**: TTS generation blocked until user approves DOCX translation table
- **Output v1**: Audio only — no video muxing

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Python over Node.js | yt-dlp, pydub, ElevenLabs ecosystem is Python-native | — Pending |
| Claude API for translation | User confirmed — best quality for nuanced JP→RU | — Pending |
| ElevenLabs for TTS | User explicitly specified — neural voice synthesis | — Pending |
| DOCX review before TTS | User confirmed — quality gate before expensive API calls | — Pending |
| Audio-only output v1 | User confirmed — video muxing deferred to v2 | — Pending |
| Claude Code skill wrapper | User confirmed — `/translate-video` slash command | — Pending |

---
*Last updated: 2026-03-04 after initialization*
