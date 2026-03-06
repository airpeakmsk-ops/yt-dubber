# Phase 5: Audio Assembly - Research

**Researched:** 2026-03-06
**Domain:** Python audio time-stretching, PCM stitching, MP3 encoding
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Stretch limit behavior (out-of-range ratios)**
- **> 1.75x (TTS too short for slot):** Play audio at native speed without stretching; pad remainder of slot with silence. Speech does not get distorted.
- **< 0.60x (TTS too long for slot):** Clamp at 0.60x (apply maximum compression); remainder of slot filled with silence (i.e., compressed audio still fits within slot, the over-compressed tail is silenced).
- **WARN logging:** Any clamped segment must emit a warning: `WARN: seg_{index:04d} clamped (ratio {actual:.2f}x → {limit:.2f}x)`.
- **Inter-segment gaps:** Time between end of segment N and start of segment N+1 is filled with silence. This is inherent to the absolute-timecode approach and correctly reproduces original video pauses.

**MP3 output quality**
- **Bitrate:** 192 kbps
- **Sample rate:** 22050 Hz — native ElevenLabs PCM rate; no resampling needed, faster assembly.
- **Loudness normalization:** None
- **Assembly progress log:**
  - Start: `Assembling {N} segments...`
  - Done: `Done: {output_path}`

**Track length and output naming**
- **total_ms computation:** `assemble_track` computes `total_ms` internally as `int(max(seg.end_sec for seg in segments) * 1000)`. The `total_ms` parameter is kept but made `Optional[int] = None` — if provided, it overrides; if None, auto-computed.
- **Trailing silence:** Track ends immediately after the last segment — no trailing silence added.
- **Default output filename:** `{output_dir}/{video_id}_dubbed_ru.mp3`
- **Format:** MP3 default (existing `fmt="mp3"` stub parameter retained as-is).

### Claude's Discretion
- Stretch library selection: pyrubberband (if rubberband.exe available on Windows) with librosa fallback — Claude picks the fallback detection strategy.
- Audio assembly library: pydub, soundfile, or wave stdlib — Claude selects based on research.
- Exact PCM stitching and MP3 encoding mechanics (sample alignment, mono channel handling).
- WAV-to-PCM conversion pipeline before assembly.

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| AUDI-01 | Each audio segment is time-stretched/compressed to match original subtitle slot duration | `stretch_to_duration()` in `audio_sync.py`: librosa `time_stretch` as primary (Windows-safe), pyrubberband as optional upgrade. Clamp 0.60x–1.75x with silence padding. |
| AUDI-02 | Track assembled using absolute timecode positions (no cumulative drift) | NumPy buffer pattern: allocate `total_ms` silence array, write each segment at `start_sec * sample_rate` offset. No pydub overlay loop needed. |
| AUDI-03 | User receives final dubbed audio track (MP3/WAV) named `<video_id>_dubbed_ru.mp3` | `lameenc` for pure-Python MP3 encoding at 192 kbps / 22050 Hz / mono. No ffmpeg dependency. |
</phase_requirements>

---

## Summary

Phase 5 implements two modules: `audio_sync.stretch_to_duration()` (time-stretch one WAV segment to a target duration in ms) and `merger.assemble_track()` (place all stretched segments on an absolute-timecode silence canvas and encode to MP3).

The critical environmental fact is that this project runs on Windows and **ffmpeg, rubberband.exe, pydub, librosa, soundfile, and pyrubberband are not yet installed** — only `numpy` is present. The MP3 encoding path using pydub requires ffmpeg, which is absent. The correct encoding path is `lameenc` (pure-Python LAME bindings, no subprocess, no system binary, pip-installable, released 2025-01-01). For time-stretching, `librosa` is the safe primary choice on Windows; `pyrubberband` is listed as an optional extra in `pyproject.toml` precisely because it requires a separate `rubberband.exe` CLI binary that is not pip-installable.

The assembly algorithm must use a NumPy sample buffer rather than a pydub `overlay()` loop. The pydub overlay pattern is pure-Python and degrades severely with many calls (documented: 20k segments → hours). The correct pattern is: allocate a `numpy.zeros(total_samples, dtype=int16)` buffer, read each WAV via `soundfile.read()` as int16, slice-assign at the correct sample offset. This is O(N) in total samples, not O(N²) in segments.

**Primary recommendation:** Install `soundfile`, `librosa`, and `lameenc` as required dependencies. Use `librosa.effects.time_stretch` for all stretching (no rubberband.exe needed). Assemble via NumPy int16 buffer. Encode to MP3 via `lameenc`. No ffmpeg required anywhere.

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| librosa | >=0.10.0 (already in pyproject.toml) | Time-stretch WAV numpy array via phase vocoder | Pure-Python, pip-installable, Windows-safe; already declared dependency |
| soundfile | >=0.12.0 (already in pyproject.toml) | Read WAV files as numpy int16/float32 arrays | libsndfile wheels ship for Windows; no external binary needed |
| numpy | >=1.24.0 (already in pyproject.toml, **installed: 2.4.2**) | Allocate silence buffer, sample-accurate placement | Already installed; slice-assign is O(1) per segment |
| lameenc | >=1.7.0 (NOT in pyproject.toml — must add) | Encode numpy int16 → MP3 bytes without ffmpeg | Pure-Python LAME bindings, v1.8.1 released 2025-01-01, no subprocess |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyrubberband | >=0.3.0 (optional extra, already in pyproject.toml) | Higher-quality phase-coherent time-stretch | Only when `rubberband.exe` is on PATH; never on bare Windows |
| wave (stdlib) | stdlib | Read WAV header to get sample rate / n_channels | Already used in tts.py; fallback if soundfile unavailable |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| lameenc | pydub export("mp3") | pydub requires ffmpeg system binary for MP3; ffmpeg is not installed and is a heavy dependency |
| librosa.effects.time_stretch | pyrubberband.time_stretch | pyrubberband requires rubberband.exe on Windows — not pip-installable; use as optional upgrade only |
| numpy int16 buffer + lameenc | pydub AudioSegment chain | pydub overlay() in pure Python is O(N) per call creating new object each time; degrades to hours at 100+ segments |
| soundfile.read() | wave stdlib | soundfile returns numpy array directly; wave requires manual struct unpacking |

**Installation (Wave 0 task):**
```bash
pip install librosa soundfile lameenc
# pyrubberband is optional-extra, skip unless rubberband.exe is confirmed on PATH
```

**pyproject.toml update required:** Add `lameenc>=1.7.0` to `[project.dependencies]`.

---

## Architecture Patterns

### Recommended Module Structure

```
yt_dubber/
├── audio_sync.py    # stretch_to_duration(audio_path, target_ms) -> bytes
│                    #   reads WAV via soundfile, librosa.time_stretch, returns WAV bytes
├── merger.py        # assemble_track(segments, total_ms, output_path, fmt, stretch) -> str
│                    #   numpy buffer, slice-assign each segment, lameenc → MP3
└── models.py        # SubtitleSegment.audio_path, .start_sec, .end_sec, .duration_sec (unchanged)

tests/
└── test_assembly.py # TDD: test_stretch_to_duration_*, test_assemble_track_*
```

### Pattern 1: stretch_to_duration — librosa phase vocoder with clamp

**What:** Read WAV as float32 numpy array via soundfile, compute ratio = `tts_duration_ms / target_ms`, apply clamp logic, call `librosa.effects.time_stretch`, return WAV bytes.

**When to use:** Always — this is the only implementation. pyrubberband is an optional upgrade path.

**Ratio clamp logic (locked by CONTEXT.md):**
```python
# Source: CONTEXT.md decisions
RATIO_MIN = 0.60   # maximum compression — below this, clamp + pad with silence
RATIO_MAX = 1.75   # maximum stretch — above this, use native speed + pad with silence

tts_ms = actual WAV duration in ms (from soundfile frames / samplerate * 1000)
ratio  = tts_ms / target_ms   # < 1 = compress (TTS longer than slot), > 1 = stretch (TTS shorter)

if ratio > RATIO_MAX:
    # TTS too short: play at native speed, pad tail with silence
    print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x → 1.00x)")
    stretched_audio = original_audio  # no stretch
    # silence pad = (target_ms - tts_ms) ms
elif ratio < RATIO_MIN:
    # TTS too long: clamp to 0.60x, pad tail with silence
    print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x → {RATIO_MIN:.2f}x)")
    stretched_audio = librosa.effects.time_stretch(y, rate=RATIO_MIN)
    # silence pad fills remainder of slot
else:
    stretched_audio = librosa.effects.time_stretch(y, rate=ratio)
    # no padding needed
```

**Important:** `librosa.effects.time_stretch(y, rate=r)` where `rate > 1` speeds up (compresses), `rate < 1` slows down (stretches). This is the **inverse** of what "stretch ratio" intuitively means. When TTS is shorter than slot, we want to slow it down — that means `rate = tts_ms / target_ms < 1`. The naming is consistent: ratio = tts/target, and librosa rate = tts/target.

**Return WAV bytes via soundfile + io.BytesIO:**
```python
import io, soundfile as sf, numpy as np

buf = io.BytesIO()
# soundfile expects shape (frames,) for mono or (frames, channels) for stereo
sf.write(buf, audio_out, samplerate=22050, format="WAV", subtype="PCM_16")
buf.seek(0)
return buf.read()
```

### Pattern 2: assemble_track — NumPy int16 buffer with sample-accurate placement

**What:** Allocate a zeros array of `total_samples = total_ms * 22050 // 1000` samples. For each segment, read its WAV bytes (from `stretch_to_duration`) into a numpy int16 array. Slice-assign at `start_sample = int(seg.start_sec * 22050)`.

**When to use:** Always. This replaces the pydub overlay loop entirely.

```python
# Source: WebSearch (verified pattern from pydub performance issue research)
import numpy as np
import io, soundfile as sf

SAMPLE_RATE = 22050

total_samples = total_ms * SAMPLE_RATE // 1000
canvas = np.zeros(total_samples, dtype=np.int16)

for seg in segments:
    if seg.audio_path is None or seg.status not in (SegmentStatus.TTS_DONE, SegmentStatus.SKIPPED):
        continue  # ERROR segments: slot stays silence

    wav_bytes = stretch_to_duration(seg.audio_path, int(seg.duration_sec * 1000))
    seg_array, _ = sf.read(io.BytesIO(wav_bytes), dtype="int16", always_2d=False)

    start = int(seg.start_sec * SAMPLE_RATE)
    end   = start + len(seg_array)

    # Guard: never write past canvas boundary
    if end > total_samples:
        seg_array = seg_array[:total_samples - start]
        end = total_samples

    canvas[start:end] = seg_array
```

### Pattern 3: lameenc MP3 encoding — no ffmpeg

**What:** Encode the final `canvas` numpy int16 array to MP3 bytes at 192 kbps / 22050 Hz.

```python
# Source: lameenc PyPI docs (https://pypi.org/project/lameenc/)
import lameenc

encoder = lameenc.Encoder()
encoder.set_bit_rate(192)          # 192 kbps
encoder.set_in_sample_rate(22050)  # native ElevenLabs rate
encoder.set_channels(1)            # mono (ElevenLabs outputs mono)
encoder.set_quality(2)             # 0=best, 9=fastest; 2 = high quality

mp3_data  = encoder.encode(canvas.tobytes())
mp3_data += encoder.flush()

with open(output_path, "wb") as f:
    f.write(mp3_data)
```

### Pattern 4: pyrubberband fallback detection

**What:** Try to import pyrubberband and verify rubberband CLI is callable. If either fails, fall back to librosa.

```python
def _time_stretch(y: np.ndarray, rate: float, sr: int) -> np.ndarray:
    """Stretch y at given rate. rate > 1 = speed up, < 1 = slow down."""
    try:
        import pyrubberband as pyrb
        return pyrb.time_stretch(y, sr, rate)
    except Exception:
        # pyrubberband not installed, or rubberband.exe not on PATH
        import librosa
        return librosa.effects.time_stretch(y, rate=rate)
```

This is the detection strategy chosen for Claude's Discretion: wrap pyrubberband in a broad `except Exception` so any failure (ImportError, RuntimeError from missing CLI, FileNotFoundError) falls through to librosa. No explicit PATH check required.

### Anti-Patterns to Avoid

- **pydub overlay() loop for assembly:** Creates a new AudioSegment object per call; pure-Python loop is O(N) allocations. With 100+ segments over a 30-minute video, this becomes minutes of CPU. Use numpy buffer slice-assign instead.
- **pydub export("mp3") for encoding:** Requires ffmpeg system binary. ffmpeg is not installed on this machine. Use lameenc instead.
- **Calling librosa.load() instead of soundfile.read():** `librosa.load()` resamples to 22050 Hz by default AND converts to float32 — both are fine, but it is slower and imports more. For this pipeline, `soundfile.read(path, dtype="float32")` is sufficient and faster.
- **Assuming stereo input from ElevenLabs:** All WAVs written by `tts.py` are mono 22050 Hz 16-bit (verified in `_write_pcm_as_wav` and `_write_silence`). Never set `set_channels(2)` in lameenc.
- **Integer overflow in canvas addition:** Using `canvas[start:end] += seg_array` for overlapping segments risks int16 overflow. Use assignment `=` not `+=` — segments never overlap by design (absolute timecodes, no bleeding).
- **Wrong librosa rate direction:** `librosa.effects.time_stretch(y, rate=2.0)` speeds up by 2x (compresses). `rate=0.5` slows down 2x (stretches). ratio = `tts_ms / target_ms` aligns with librosa's rate parameter correctly: when TTS is shorter than slot, ratio < 1, librosa slows it down to fill the slot.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MP3 encoding | Custom ffmpeg subprocess wrapper | lameenc | ffmpeg not installed; subprocess adds fragility; lameenc is pure-Python LAME bindings |
| Time-stretching | Custom pitch-preserving resampler | librosa.effects.time_stretch | Phase vocoder is mathematically complex; librosa is the standard Python implementation |
| WAV parsing | struct.unpack() PCM bytes manually | soundfile.read() | WAV has many subformat variants (PCM_16, PCM_24, float32, extensible RIFF); soundfile handles all |
| Silence padding bytes | Manual zero-byte calculation | numpy.zeros(n, dtype=int16) | Already in canvas; just don't write to that region |

**Key insight:** The three hard problems here — time-stretching, MP3 encoding, WAV I/O — each have a single correct library. Using anything else means reimplementing decades of DSP work.

---

## Common Pitfalls

### Pitfall 1: ffmpeg Required for pydub MP3 Export

**What goes wrong:** Developer writes `segment.export(path, format="mp3")` — pydub silently creates a 0-byte MP3 file if ffmpeg is not on PATH. No exception is raised in some configurations.
**Why it happens:** pydub delegates encoding to ffmpeg subprocess. When ffmpeg is missing, it may silently fail.
**How to avoid:** Do not use pydub for MP3 export. Use `lameenc` exclusively.
**Warning signs:** MP3 output file is 0 bytes; `pydub.utils.which("ffmpeg")` returns None.

### Pitfall 2: librosa time_stretch rate direction confusion

**What goes wrong:** Developer passes `rate = target_ms / tts_ms` (inverse), causing TTS-too-short segments to be compressed further and TTS-too-long segments to be stretched even longer.
**Why it happens:** "stretch ratio" is ambiguous — it can mean "how much to stretch the output" vs. "speed multiplier applied to input".
**How to avoid:** Always compute `rate = tts_ms / target_ms`. When `tts_ms < target_ms` (short TTS, needs to stretch), rate < 1 → librosa slows it down (stretches). Matches intuition.
**Warning signs:** Assembled track duration is wrong; segments that should be silent-padded are instead sped up.

### Pitfall 3: pyrubberband Fails Silently on Windows

**What goes wrong:** `import pyrubberband` succeeds (package is installed), but calling `pyrb.time_stretch()` raises `RuntimeError: Failed to execute rubberband. Please verify that rubberband-cli is installed.`
**Why it happens:** pyrubberband is a thin wrapper around the `rubberband` command-line binary. The Python package installs fine; the binary does not.
**How to avoid:** Wrap pyrubberband call in `try/except Exception` and fall back to librosa. Test fallback explicitly in test suite.
**Warning signs:** RuntimeError mentioning "rubberband-cli" at runtime; no error at import time.

### Pitfall 4: soundfile.read() returns float32, lameenc expects int16

**What goes wrong:** `sf.read(path)` returns float64 or float32 by default. Passing float array to `encoder.encode()` produces garbled audio.
**Why it happens:** soundfile defaults to `dtype=float64`. lameenc's `encode()` expects raw int16 PCM bytes.
**How to avoid:** Always read with `sf.read(path, dtype="float32")` then convert: `(audio * 32767).astype(np.int16)`. Or read with `dtype="int16"` directly when input is known PCM_16.
**Warning signs:** MP3 output plays as white noise or is silent; audio duration is correct but content is garbage.

### Pitfall 5: Canvas Boundary Overrun

**What goes wrong:** A stretched segment's sample array is longer than `total_samples - start`, causing `canvas[start:end] = seg_array` to raise IndexError or silently truncate.
**Why it happens:** Floating-point rounding in `total_ms` computation vs. actual stretched audio length; also happens when a segment's `end_sec` exactly equals `max(end_sec)` but stretch adds a few samples.
**How to avoid:** Always guard: `seg_array = seg_array[:total_samples - start]` before slice-assign.
**Warning signs:** IndexError in assembly loop; last segment is cut off.

### Pitfall 6: lameenc Not in pyproject.toml

**What goes wrong:** lameenc is not currently declared in `pyproject.toml` dependencies. A clean install of the project (`pip install -e .`) will not install lameenc, causing ImportError at runtime.
**How to avoid:** Wave 0 task must add `lameenc>=1.7.0` to `[project.dependencies]` in `pyproject.toml`.

---

## Code Examples

Verified patterns from official sources and project context:

### stretch_to_duration — complete flow

```python
# Source: librosa docs + soundfile docs + CONTEXT.md locked decisions
from __future__ import annotations
import io
import numpy as np
import soundfile as sf
import librosa

SAMPLE_RATE = 22050
RATIO_MIN   = 0.60
RATIO_MAX   = 1.75


def _time_stretch(y: np.ndarray, rate: float, sr: int) -> np.ndarray:
    try:
        import pyrubberband as pyrb
        return pyrb.time_stretch(y, sr, rate)
    except Exception:
        return librosa.effects.time_stretch(y, rate=rate)


def stretch_to_duration(audio_path: str, target_ms: int, index: int = 0) -> bytes:
    y, sr = sf.read(audio_path, dtype="float32", always_2d=False)
    if sr != SAMPLE_RATE:
        y = librosa.resample(y, orig_sr=sr, target_sr=SAMPLE_RATE)

    tts_ms = len(y) / SAMPLE_RATE * 1000
    ratio  = tts_ms / target_ms  # < 1 = slow down, > 1 = speed up

    if ratio > RATIO_MAX:
        # TTS too short for slot: native speed + silence pad
        print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x → 1.00x)")
        stretched = y
    elif ratio < RATIO_MIN:
        # TTS too long for slot: clamp at 0.60x + silence pad
        print(f"WARN: seg_{index:04d} clamped (ratio {ratio:.2f}x → {RATIO_MIN:.2f}x)")
        stretched = _time_stretch(y, RATIO_MIN, SAMPLE_RATE)
    else:
        stretched = _time_stretch(y, ratio, SAMPLE_RATE)

    # Trim or pad to exactly target_ms
    target_samples = int(target_ms * SAMPLE_RATE / 1000)
    if len(stretched) >= target_samples:
        out = stretched[:target_samples]
    else:
        pad = np.zeros(target_samples - len(stretched), dtype=np.float32)
        out = np.concatenate([stretched, pad])

    buf = io.BytesIO()
    sf.write(buf, out, SAMPLE_RATE, format="WAV", subtype="PCM_16")
    buf.seek(0)
    return buf.read()
```

### assemble_track — NumPy buffer + lameenc

```python
# Source: lameenc PyPI docs + numpy slice pattern
from __future__ import annotations
import io
from typing import List, Optional
import numpy as np
import soundfile as sf
import lameenc

from yt_dubber.models import SubtitleSegment, SegmentStatus, JobState
from yt_dubber.config import settings
from yt_dubber.audio_sync import stretch_to_duration

SAMPLE_RATE = 22050


def assemble_track(
    segments: List[SubtitleSegment],
    total_ms: Optional[int] = None,
    output_path: Optional[str] = None,
    fmt: str = "mp3",
    stretch: bool = True,
    job: Optional[JobState] = None,
) -> str:
    if total_ms is None:
        total_ms = int(max(seg.end_sec for seg in segments) * 1000)

    if output_path is None:
        video_id = job.video_id if job else "output"
        output_path = f"{settings.output_dir}/{video_id}_dubbed_ru.mp3"

    total_samples = int(total_ms * SAMPLE_RATE / 1000)
    canvas = np.zeros(total_samples, dtype=np.int16)

    active = [s for s in segments if s.audio_path and s.status in
              (SegmentStatus.TTS_DONE, SegmentStatus.SKIPPED)]
    print(f"Assembling {len(active)} segments...")

    for seg in active:
        target_ms = int(seg.duration_sec * 1000)
        wav_bytes  = stretch_to_duration(seg.audio_path, target_ms, index=seg.index)
        seg_arr, _ = sf.read(io.BytesIO(wav_bytes), dtype="int16", always_2d=False)

        start = int(seg.start_sec * SAMPLE_RATE)
        end   = start + len(seg_arr)
        if end > total_samples:
            seg_arr = seg_arr[: total_samples - start]
            end = total_samples
        canvas[start:end] = seg_arr

    # Encode to MP3
    encoder = lameenc.Encoder()
    encoder.set_bit_rate(192)
    encoder.set_in_sample_rate(SAMPLE_RATE)
    encoder.set_channels(1)
    encoder.set_quality(2)
    mp3_data  = encoder.encode(canvas.tobytes())
    mp3_data += encoder.flush()

    with open(output_path, "wb") as f:
        f.write(mp3_data)

    print(f"Done: {output_path}")
    return output_path
```

### Test fixture pattern (consistent with existing test_tts.py style)

```python
# Source: tests/test_tts.py — established project pattern
import wave, io, pathlib
import numpy as np
import pytest
from yt_dubber.models import SubtitleSegment, SegmentStatus


def make_wav_bytes(duration_sec: float = 1.0, sr: int = 22050) -> bytes:
    """Generate a silent mono WAV for test fixtures (no file I/O needed)."""
    n_frames = int(sr * duration_sec)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(b"\x00" * n_frames * 2)
    buf.seek(0)
    return buf.read()


def make_segment(index, start_sec, end_sec, status=SegmentStatus.TTS_DONE,
                 audio_path=None) -> SubtitleSegment:
    return SubtitleSegment(
        index=index, start_sec=start_sec, end_sec=end_sec,
        duration_sec=end_sec - start_sec,
        jp_text="テスト", ru_text="тест", audio_path=audio_path, status=status,
    )
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| pydub overlay() loop | NumPy int16 buffer + slice-assign | 2024 community finding | Orders of magnitude faster for 50+ segments |
| pydub export("mp3") | lameenc pure-Python binding | ffmpeg-less environments | Eliminates system binary dependency |
| pyrubberband only | librosa primary + pyrubberband optional | pyrubberband Windows issue | Reliable on Windows without PATH surgery |

**Deprecated/outdated for this project:**
- `pydub.AudioSegment` as assembly layer: viable for 2-5 segments; not for full video dubbing tracks.
- `audioop` stdlib module: removed in Python 3.13; do not use for sample manipulation.

---

## Open Questions

1. **lameenc mono encoding of a stereo numpy array**
   - What we know: lameenc `set_channels(1)` + a mono int16 array works.
   - What's unclear: If somehow a segment WAV is stereo (e.g., a file written by a different tool), passing a 2D array will break.
   - Recommendation: In `stretch_to_duration`, always call `sf.read(..., always_2d=False)` and add `if y.ndim > 1: y = y[:, 0]` to force mono. Confirm in test.

2. **librosa.effects.time_stretch on very short segments (<200ms)**
   - What we know: librosa uses STFT internally; very short segments may not have enough frames for the FFT window.
   - What's unclear: Whether it raises, returns silence, or returns garbled audio below ~100ms.
   - Recommendation: Add a guard: if `len(y) < 512`, skip time_stretch and return original audio (or silence pad directly). Test with 50ms, 100ms, 200ms segments.

3. **lameenc output file size for very short tracks (< 1 second)**
   - What we know: lameenc requires `encoder.flush()` to emit trailing MP3 frames.
   - What's unclear: Whether a 0-frame canvas (no active segments) produces a valid (empty) MP3.
   - Recommendation: Guard `if not active: write silence canvas and proceed normally` — the canvas is already zeros, so encoding zeros is safe.

---

## Sources

### Primary (HIGH confidence)
- lameenc PyPI: https://pypi.org/project/lameenc/ — encoder API, set_bit_rate/set_channels/encode/flush, v1.8.1 (2025-01-01)
- soundfile docs: https://python-soundfile.readthedocs.io/en/0.13.1/ — sf.read dtype parameter, always_2d, BytesIO support
- librosa docs (via WebSearch cross-referenced with official readthedocs): `librosa.effects.time_stretch(y, rate=r)` — rate > 1 speeds up, rate < 1 slows down
- pydub GitHub API.markdown: https://github.com/jiaaro/pydub/blob/master/API.markdown — overlay(position=ms, expand=True), export(format, bitrate)
- tts.py (project source): Confirmed mono, 22050 Hz, 16-bit WAV format from `_write_pcm_as_wav` and `_write_silence`

### Secondary (MEDIUM confidence)
- pyrubberband GitHub issue #18: https://github.com/bmcfee/pyrubberband/issues/18 — confirmed rubberband-cli not pip-installable on Windows
- pydub issue #550: https://github.com/jiaaro/pydub/issues/550 — confirmed overlay() pure-Python O(N) performance issue
- WebSearch (multiple sources agree): pydub export("mp3") requires ffmpeg; 0-byte output when ffmpeg missing

### Tertiary (LOW confidence)
- librosa time_stretch behavior below 512 frames — not verified against official docs; flagged as Open Question 2

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — lameenc, soundfile, librosa are all verified against official docs/PyPI; ffmpeg absence verified on machine
- Architecture: HIGH — numpy buffer pattern verified via pydub issue tracker; lameenc encoding pattern verified against PyPI docs
- Pitfalls: HIGH for ffmpeg/pyrubberband/rate-direction issues (multiple independent sources); MEDIUM for short-segment librosa edge case (Open Question 2)

**Research date:** 2026-03-06
**Valid until:** 2026-04-06 (lameenc, librosa, soundfile are stable; 30-day window appropriate)
