from __future__ import annotations
import sys
import os

# Windows encoding fix — MUST run before any console output.
# Place here (top of module) not inside if __name__ == "__main__",
# because pip installs a wrapper script that imports this module directly.
if sys.platform == "win32":
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

import click
from yt_dubber.config import settings  # noqa: F401 — triggers load_dotenv() at import


@click.group()
def cli():
    """YT-Dubber: Japanese YouTube video dubbing pipeline."""
    pass


@cli.command()
@click.argument("url")
@click.option("--output-dir", default="./output", show_default=True,
              help="Directory to write output files")
@click.option("--batch-size", default=20, show_default=True,
              help="Number of subtitle segments per Claude API call")
@click.option("--model", default=None,
              help="Claude model to use (overrides CLAUDE_MODEL in .env)")
def translate(url: str, output_dir: str, batch_size: int, model: str | None) -> None:
    """Extract Japanese subtitles and translate to Russian. Writes review DOCX."""
    raise NotImplementedError(
        "Phase 2/3 not yet implemented. "
        "Run after Phases 2 (subtitle extraction) and 3 (translation) are complete."
    )


@cli.command()
@click.argument("docx_file")
@click.option("--voice-id", default=None,
              help="ElevenLabs voice ID (overrides ELEVENLABS_VOICE_ID in .env)")
@click.option("--format", "fmt", default="mp3", show_default=True,
              type=click.Choice(["mp3", "wav"]),
              help="Output audio format")
@click.option("--resume", is_flag=True,
              help="Skip segments already marked tts_done in the job checkpoint")
@click.option("--no-stretch", is_flag=True,
              help="Disable time-stretching (use TTS audio at native length)")
@click.option("--min-duration", default=0.5, show_default=True,
              help="Minimum segment duration in seconds for TTS synthesis")
def dub(docx_file: str, voice_id: str | None, fmt: str,
        resume: bool, no_stretch: bool, min_duration: float) -> None:
    """Read reviewed DOCX, synthesize Russian TTS audio, and assemble dubbed track."""
    raise NotImplementedError(
        "Phases 4/5 not yet implemented. "
        "Run after Phases 4 (TTS synthesis) and 5 (audio assembly) are complete."
    )


if __name__ == "__main__":
    cli()
