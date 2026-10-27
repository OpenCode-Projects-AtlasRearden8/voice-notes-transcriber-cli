# voice-notes-transcriber (`vnt`)

A **local-first CLI** that turns phone voice memos into tidy, dated, searchable
Markdown notes.

You send yourself (or sync) a pile of voice memos. `vnt` transcribes them with
whatever local ASR you already have (a configurable whisper.cpp/whisper-cli
command), falls back to any configurable OpenAI-compatible endpoint when the
local command is missing (default: Ollama at `http://localhost:11434/v1`),
generates a one-line summary and a short title, and files each transcript as a
dated note:

```
notes/
  2026/
    10/
      2026-10-27-grocery-list-reminder.md
      2026-10-27-dentist-appointment.md
```

No cloud. No accounts. **No API keys — ever.** The tool never stores, sends,
or asks for a key; it only talks to your local ASR command and to keyless,
local OpenAI-compatible endpoints (like Ollama).

Part of a family of plain-English tools:

- **chat-export-archiver-cli** — archives text chats (WhatsApp/iMessage exports)
- **meeting-notes-summarizer-cli** — tidies up meeting text transcripts
- **voice-notes-transcriber** (this tool) — spoken memos become written notes

---

## How it works

For each audio file (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.flac`, `.aac`, `.opus`,
`.webm`, `.amr`, `.3gp`, `.wma` by default):

1. **Transcribe** — run your local ASR command (e.g. whisper.cpp). If that is
   not configured or fails, POST the audio to your endpoint's
   `/v1/audio/transcriptions` (many OpenAI-compatible servers, such as LM
   Studio or a whisper server, support this).
2. **Summarize** — ask the endpoint's `/v1/chat/completions` for a short title
   and a one-line summary. If no endpoint is available, a local heuristic
   builds them from the transcript.
3. **File it** — write `notes/YYYY/MM/YYYY-MM-DD-<title-slug>.md`, using the
   recording's file date (mtime). Existing filenames get `-2`, `-3`, ... suffixes
   instead of being overwritten.

Note format:

```markdown
---
title: "Please buy eggs and coffee tomorrow"
date: "2026-10-27 05:36"
summary: "Please buy eggs and coffee tomorrow morning."
source: "memo1.m4a"
transcriber: "whisper-cli"
summarizer: "endpoint:llama3.2"
---

# Please buy eggs and coffee tomorrow

Please buy eggs and coffee tomorrow morning.

## Transcript

Please buy eggs and coffee tomorrow morning. We're out of both.
```

## Quick start

Python 3.11+ required (standard library only — no third-party dependencies).

```bash
# 1. Install (into a venv if your system prefers it)
python3 -m venv .venv && source .venv/bin/activate
pip install .

# 2. Generate a starter config
vnt init

# 3. Edit vnt.toml — point asr_command at your local ASR
#    (see "Local ASR" below)

# 4. Check everything is wired up
vnt doctor

# 5. Process some memos
vnt process Downloads/voice-memos/          # a folder of loose files
vnt process --recursive ~/Sync/memos/       # include subfolders
vnt process recording.m4a                   # or one at a time

# 6. Find things later
vnt search eggs
vnt search "dentist Thursday"
```

Tip: running `vnt recording.m4a` (bare paths, no subcommand) is shorthand for
`vnt process recording.m4a`.

## Local ASR (`asr_command`)

`vnt` runs **your** transcription command. The rules:

- The command template must contain `{input}` — that is replaced by the audio
  file path.
- The command must **print the transcript text to stdout**.

### whisper.cpp / whisper-cli example

Build [whisper.cpp](https://github.com/ggml-org/whisper.cpp), download a
model (e.g. `ggml-base.en.bin`), and use `whisper-cli`, which prints segments
to stdout:

```toml
asr_command = "whisper-cli -m ~/.cache/whisper/ggml-base.en.bin -nt -f {input}"
```

- `-nt` = no timestamps (plain text out)
- `-np` also hides the progress noise, if you like quieter logs

Any other local tool works the same way, as long as it prints to stdout — a
small wrapper script around whisper.cpp, `vosk-cli`, `faster-whisper`, etc.

## The endpoint (summary + fallback transcription)

Used for three things: the fallback transcription (when no local ASR command
is configured or it fails), and the title + one-line summary. Default base URL
is Ollama's OpenAI-compatible API:

```toml
base_url = "http://localhost:11434/v1"
# llm_model = "llama3.2"        # optional; auto-detected from /v1/models if not set
# transcribe_model = "whisper-1" # optional; used only for the transcription fallback
```

Notes:

- Ollama does not (yet) serve audio transcriptions; the transcription fallback
  is aimed at OpenAI-compatible whisper servers (e.g. LM Studio,
  faster-whisper-server, whisper.cpp server mode with OpenAI protocol).
- Model selection is automatic: the CLI asks `/v1/models` and picks a model
  (preferring anything whisper-like for transcription). Set `llm_model` /
  `transcribe_model` to pin your own.
- If the endpoint is unreachable, notes are still written — title and summary
  come from a local heuristic, and the note's front matter records
  `summarizer: "local-fallback"`.

## Config (`vnt.toml`)

Run `vnt init` for a commented template. Precedence: command flags
> environment (`VNT_NOTES_DIR`, `VNT_ASR_COMMAND`, `VNT_BASE_URL`,
`VNT_LLM_MODEL`, `VNT_TRANSCRIBE_MODEL`) > `./vnt.toml` >
`~/.config/vnt/vnt.toml` > defaults.

| Key                 | Default                        | Meaning                              |
|---------------------|--------------------------------|--------------------------------------|
| `notes_dir`         | `notes`                        | where dated notes are written        |
| `asr_command`       | *(unset)*                      | local ASR command with `{input}`     |
| `base_url`          | `http://localhost:11434/v1`    | OpenAI-compatible base URL           |
| `llm_model`         | *(auto)*                       | model for title/summary              |
| `transcribe_model`  | *(auto)*                       | model for transcription fallback     |
| `asr_timeout`       | `600.0`                        | seconds for ASR steps                |
| `chat_timeout`      | `120.0`                        | seconds for the summary call         |
| `llm_max_chars`     | `8000`                         | transcript chars sent for summary    |
| `audio_extensions`  | *(list above)*                 | file types treated as audio          |
| `offline`           | `false`                        | never touch the endpoint             |

Environment variables instead of a config file work too, e.g.:

```bash
VNT_ASR_COMMAND="whisper-cli -m ~/.cache/whisper/ggml-base.en.bin -nt -f {input}" \
  vnt process recording.m4a
```

## CLI reference

```
vnt process [inputs...]   transcribe files/folders into dated notes
  --recursive             include audio files in subfolders
  --dry-run               show would-be titles/summaries, write nothing
  --date YYYY-MM-DD       override the note date (default: file mtime)
  --asr-command "..."     override config's asr_command
  --offline               endpoint never contacted (local ASR only)
vnt init                  write a starter vnt.toml (refuses to overwrite)
vnt search QUERY          case-insensitive search across your notes
vnt doctor                check config, ASR command, and endpoint health
vnt --version             show version
```

Exit codes: `0` success, `1` processing failure (per-file errors are reported
and the run continues), `2` usage/config error.

## Privacy, in plain English

- Audio files are read only by your own local tools.
- The transcript goes to exactly one place for summarization: the base URL you
  configured. Set `offline = true` (or `--offline`) and the endpoint is never
  contacted at all.
- Only the note's front matter stores the **filename** of the audio — never
  full paths, never personal metadata beyond what you typed.
- There are no key settings because there is no need: the tool is designed for
  keyless local endpoints. If your "OpenAI-compatible" server needs a key,
  this tool is not designed for it on purpose.

## Development

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

The test suite uses a **fake ASR command** (`tests/fake_asr.py`) and a fake
OpenAI-compatible endpoint server on localhost, so nothing here touches the
network or requires models.

## Credits

Built by **Asdale Dynamics, LLC** — plain-English AI education, books, and
practical local-first tools. See [dylanasdale.github.io](https://dylanasdale.github.io)
and *The Massive AI Manual* for the friendly, step-by-step companion material.

Licensed under the MIT License (see `LICENSE`).
Copyright (c) 2026 Asdale Dynamics, LLC.
