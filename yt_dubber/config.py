from __future__ import annotations
import os
from dataclasses import dataclass

from dotenv import load_dotenv

# CRITICAL: load_dotenv() MUST come before Settings instantiation.
# It populates os.environ from .env; if called after os.getenv() reads,
# all config fields will be empty strings.
load_dotenv()


@dataclass(frozen=True)
class Settings:
    anthropic_api_key:          str   = ""
    elevenlabs_api_key:         str   = ""
    elevenlabs_voice_id:        str   = "Vl27Cllkuw8BhyPqus2n"  # VASKO voice
    elevenlabs_model:           str   = "eleven_multilingual_v2"
    elevenlabs_stability:       float = 0.85
    elevenlabs_similarity_boost: float = 0.80
    output_dir:                 str   = "./output"
    claude_model:               str   = "claude-sonnet-4-5"
    translation_batch_size:     int   = 20

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            elevenlabs_voice_id=os.getenv("ELEVENLABS_VOICE_ID", "Vl27Cllkuw8BhyPqus2n"),
            elevenlabs_model=os.getenv("ELEVENLABS_MODEL", "eleven_multilingual_v2"),
            elevenlabs_stability=float(os.getenv("ELEVENLABS_STABILITY", "0.85")),
            elevenlabs_similarity_boost=float(os.getenv("ELEVENLABS_SIMILARITY_BOOST", "0.80")),
            output_dir=os.getenv("OUTPUT_DIR", "./output"),
            claude_model=os.getenv("CLAUDE_MODEL", "claude-sonnet-4-5"),
            translation_batch_size=int(os.getenv("TRANSLATION_BATCH_SIZE", "20")),
        )


# Module-level singleton — import as: from yt_dubber.config import settings
settings = Settings.from_env()
