# STATUS — voice-notes-transcriber-cli

Date: 2026-10-27 · Owner: Asdale Dynamics, LLC · Version: 0.1.0 · License: MIT

## What was built

`vnt` — a local-first Python CLI (standard library only, Python 3.11+) that
turns phone voice memos into tidy, dated, searchable Markdown notes:

- **Local ASR first**: any configurable command (by default aimed at
  whisper.cpp/`whisper-cli`) — the command template must contain `{input}` and
  print the transcript to stdout.
- **Endpoint fallback**: any keyless OpenAI-compatible base URL
  (default `http://localhost:11434/v1` — Ollama). Used for fallback
  transcription via `POST /v1/audio/transcriptions` (multipart upload) and for
  generating a one-line summary + short title via `POST /v1/chat/completions`.
  Models are auto-detected from `GET /v1/models` if not configured.
- **Never a key**: no key config, no auth headers, no secrets anywhere.
- **Dated filing**: `notes/YYYY/MM/YYYY-MM-DD-<slug>.md` with YAML front
  matter (title, date, summary, source filename, transcriber, summarizer),
  note date defaults to the audio file's mtime; collisions get `-2`, `-3`.
- **Heuristic fallback summarizer**: if the endpoint is unreachable, a local
  first-sentence heuristic produces title/summary so no note is ever lost.
- **Subcommands**: `process` (incl. `--recursive`, `--dry-run`, `--date`,
  `--offline`), `init` (writes a commented `vnt.toml`), `search` (grep across
  notes), `doctor` (checks ASR command, endpoint, config).
- **Config**: `./vnt.toml` > `~/.config/vnt/vnt.toml`, env vars
  (`VNT_NOTES_DIR`, `VNT_ASR_COMMAND`, `VNT_BASE_URL`, `VNT_LLM_MODEL`,
  `VNT_TRANSCRIBE_MODEL`), and CLI flags — in increasing precedence. No API-key
  option exists by design.

## Layout

```
src/vnt/            package (cli, config, client, transcriber, summarizer, notes)
tests/              pytest suite + fake ASR command + fake endpoint server
pyproject.toml      packaging (console scripts: vnt, voice-notes)
LICENSE             MIT, "Copyright (c) 2026 Asdale Dynamics, LLC"
README.md           beginner-friendly usage guide, credits Asdale Dynamics, LLC
```

## How to run it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install .
vnt init && $EDITOR vnt.toml      # set asr_command for your whisper.cpp
vnt doctor                        # verify ASR/endpoint wiring
vnt process memos/                # files a folder into notes/YYYY/MM/*.md
vnt search "eggs"
```

Offline mode (`vnt process --offline` or `offline = true`) never touches the
network endpoint.

## Verification results (2026-10-27)

| Check | Result |
|---|---|
| `pytest` (system python 3.13.5) | **54 passed** |
| `pytest` inside venv against installed package | **54 passed** |
| `python3 -m compileall src tests` | OK |
| `pip install .` into clean venv | OK (`vnt` + `voice-notes` console scripts) |
| `vnt init` smoke run | wrote `vnt.toml`; second run refuses to overwrite (exit 2) |
| `vnt doctor` smoke run | correct routes reported; exit 1 when nothing available |
| `vnt process --offline ...` smoke run (3 memos, fake ASR) | 3 notes written to `notes/2026/10/`, correct titles/summaries/front matter, exit 0 |
| `vnt search eggs` smoke run | found matches, exit 0 (no match → exit 1) |
| `vnt process --dry-run` smoke run | nothing written |
| Live endpoint smoke (fake OpenAI-compatible server on localhost) | transcription fallback + title/summary via real HTTP round-trip; note filed with `transcriber: "endpoint:fake-whisper"` |
| Failure smoke (no ASR configured, dead endpoint) | exit 1, no partial notes |

Test suite details: the fake ASR command (`tests/fake_asr.py`, driven by
sidecar `.expected.txt` files) exercises the command path; a threading
stdlib HTTP server (`tests/fake_server.py`) fakes `/v1/models`,
`/v1/chat/completions`, and `/v1/audio/transcriptions` — no real network or
models required.

## Known gaps

- **No in-note speaker labels or diarization** — single-speaker assumption;
  whatever your ASR prints becomes the transcript.
- **No incremental resume/index** — reprocessing the same memo writes a
  duplicate note with a `-2` suffix rather than skipping known files.
- **Transcription fallback expects an OpenAI-format server** that accepts
  multipart `/v1/audio/transcriptions`; Ollama itself does not serve audio
  transcription (it is used for title/summary, which works).
- **Command-based ASR only, no receiver-side formats** — e.g. whisper.cpp
  JSON/SRT output is not parsed; the command must print plain text.
- **Search is plain substring** — no stemming, no token indexes; fine for
  personal note archives.
- **POSIX-oriented** — paths and shell habits assume Linux/macOS; Windows is
  untested.
- Not yet on PyPI; install from this repository.
