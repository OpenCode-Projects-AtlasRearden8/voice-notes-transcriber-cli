"""Load and write the TOML configuration template for voice-notes-transcriber."""

from __future__ import annotations

from pathlib import Path

from vnt import __version__

CONFIG_TEMPLATE = f"""\
# voice-notes-transcriber {__version__} configuration
# Point the CLI at this file with:  vnt --config {Path("vnt.toml")} process recording.m4a
# Or keep it next to where you run the CLI and it is picked up automatically.
#
# There are deliberately NO API-key options. This tool only talks to your
# local ASR command and a keyless, local OpenAI-compatible endpoint.

# Where finished notes are filed (notes/YYYY/MM/YYYY-MM-DD-title.md):
notes_dir = "notes"

# Your local ASR command. {{input}} is replaced with the audio file path.
# The command MUST print the transcript text to stdout.
# Example for whisper.cpp (whisper-cli):
#   asr_command = "whisper-cli -m ~/.cache/whisper/ggml-base.en.bin -nt -f {{input}}"
# Leave unset to use only the endpoint fallback below.
# asr_command = "whisper-cli -m ~/.cache/whisper/ggml-base.en.bin -nt -f {{input}}"

# OpenAI-compatible endpoint used for fallback transcription and for
# generating the title + one-line summary. Default is Ollama.
base_url = "http://localhost:11434/v1"

# Optional: pick specific models instead of auto-detected ones.
# llm_model = "llama3.2"
# transcribe_model = "whisper-1"

# Optional tuning (defaults shown):
# asr_timeout = 600.0        # seconds for ASR command / transcription fallback
# chat_timeout = 120.0       # seconds for the summary/title endpoint call
# llm_max_chars = 8000       # transcript characters sent for summarization
# audio_extensions = [".m4a", ".mp4", ".mp3", ".wav", ".ogg", ".flac", ".aac", ".opus", ".webm", ".amr", ".3gp", ".wma"]
"""


def write_config_template(target: Path) -> Path:
    target.write_text(CONFIG_TEMPLATE, encoding="utf-8")
    return target
