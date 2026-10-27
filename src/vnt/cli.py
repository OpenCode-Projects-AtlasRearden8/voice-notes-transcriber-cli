"""Command-line interface for voice-notes-transcriber.

Subcommands: process (default for bare audio paths), init, search, doctor.
"""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
import sys
from datetime import date, datetime, time
from pathlib import Path

from vnt import __version__, client
from vnt.config import Config, ConfigError, load_config
from vnt.config_template import write_config_template
from vnt.notes import NoteError, search_notes, write_note
from vnt.summarizer import EndpointSummarizer, SummaryChain
from vnt.transcriber import (
    CommandTranscriber,
    EndpointTranscriber,
    FallbackTranscriber,
    TranscribeError,
)

SUBCOMMANDS = ("process", "init", "search", "doctor")


def _line(text: str) -> None:
    print(text, flush=True)


def _warn(text: str) -> None:
    print(text, file=sys.stderr, flush=True)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="vnt",
        description=(
            "Local-first CLI that turns phone voice memos into tidy, dated, "
            "searchable Markdown notes (notes/YYYY/MM/*.md)."
        ),
    )
    parser.add_argument("--version", action="version", version=f"vnt {__version__}")
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--config", type=Path, default=None, help="path to a vnt.toml config file")
    common.add_argument("--notes-dir", type=Path, default=None, help="override notes output directory")
    common.add_argument("--asr-command", default=None, help="local ASR command template containing {input}")
    common.add_argument("--base-url", default=None, help="OpenAI-compatible base URL (default: Ollama)")
    common.add_argument("--llm-model", default=None, help="model for summary/title generation")
    common.add_argument("--transcribe-model", default=None, help="model for endpoint transcription fallback")
    common.add_argument("--offline", action="store_true", help="never touch the endpoint; local ASR + local heuristics only")

    sub = parser.add_subparsers(dest="command")

    process = sub.add_parser("process", parents=[common], help="transcribe audio files into notes")
    process.add_argument("inputs", nargs="*", default=[], help="audio files or folders")
    process.add_argument("--recursive", action="store_true", help="search folders recursively")
    process.add_argument("--dry-run", action="store_true", help="show what would be written; write nothing")
    process.add_argument("--date", default=None, help="override note date (YYYY-MM-DD); default is the file's mtime")

    sub.add_parser("init", parents=[common], help="write a starter vnt.toml")
    search = sub.add_parser("search", parents=[common], help="search notes for text")
    search.add_argument("query", help="text to look for")
    sub.add_parser("doctor", parents=[common], help="check local ASR and endpoint availability")
    return parser


def _overrides(args) -> dict:
    overrides = {
        "notes_dir": str(args.notes_dir) if args.notes_dir is not None else None,
        "asr_command": args.asr_command,
        "base_url": args.base_url,
        "llm_model": args.llm_model,
        "transcribe_model": args.transcribe_model,
    }
    if getattr(args, "offline", False):
        overrides["offline"] = True
    return overrides


def cmd_init(args) -> int:
    target = (args.config or Path("vnt.toml")).expanduser()
    if target.exists():
        _warn(f"refusing to overwrite existing config: {target}")
        return 2
    write_config_template(target)
    _line(f"wrote {target}")
    _line("next: edit asr_command for your local ASR, then: vnt process recording.m4a")
    return 0


def cmd_doctor(args) -> int:
    try:
        config, used_files = load_config(_overrides(args), args.config)
    except ConfigError as exc:
        _warn(f"config error: {exc}")
        return 2

    for path in used_files:
        _line(f"config file: {path}")
    notes_dir = Path(config.notes_dir).expanduser()
    _line(f"notes dir:    {notes_dir} {'(exists)' if notes_dir.is_dir() else '(missing, created on first note)'}")
    _line(f"offline mode: {'yes' if config.offline else 'no'}")

    ok_paths = []
    if config.asr_command:
        status = "ok"
        try:
            first = shlex.split(config.asr_command)[0]
            found = shutil.which(first) is not None or "/" in first or "\\" in first
            status = f"found on PATH ('{first}')" if found else f"warning: '{first}' not on PATH"
            ok_paths.append(found)
        except ValueError as exc:
            status = f"cannot parse ({exc})"
        _line(f"asr command:  {status}")
    else:
        _line("asr command:  not configured (endpoint fallback will be used)")

    reachable = False
    if config.offline:
        _line("endpoint:     skipped (offline mode)")
    else:
        _line(f"endpoint:     {config.base_url}")
        try:
            status_code, body = client.get_json(
                f"{config.base_url.rstrip('/')}/models", timeout=10.0
            )
            if status_code == 200:
                try:
                    ids = [str(item["id"]) for item in json.loads(body).get("data", [])]
                except (ValueError, KeyError, TypeError):
                    ids = []
                _line("endpoint:     reachable" + (f"; models: {', '.join(ids)}" if ids else "; no models listed (set llm_model)"))
                reachable = True
            else:
                _line(f"endpoint:     HTTP {status_code}")
        except Exception as exc:
            _line(f"endpoint:     unreachable ({exc})")

    if config.offline:
        return 0 if config.asr_command else 1
    if config.asr_command or reachable:
        return 0
    _warn("no transcription route available: configure asr_command or start your endpoint")
    return 1


def _resolve_note_date(value: str | None, audio_path: Path) -> datetime:
    if value:
        try:
            parsed = date.fromisoformat(value)
        except ValueError as exc:
            raise ConfigError(f"invalid --date value {value!r} (expected YYYY-MM-DD)") from exc
        return datetime.combine(parsed, time(12, 0))
    return datetime.fromtimestamp(audio_path.stat().st_mtime)


def _collect_inputs(
    inputs: list[str], extensions: tuple[str, ...], recursive: bool = False
) -> tuple[list[Path], int]:
    files: list[Path] = []
    problems = 0
    for raw in inputs:
        path = Path(raw).expanduser()
        if path.is_dir():
            candidates = sorted(path.rglob("*") if recursive else path.iterdir())
            found = [
                child
                for child in candidates
                if child.is_file() and child.suffix.lower() in extensions
            ]
            if not found:
                hint = "" if recursive else " (use --recursive for subfolders)"
                _warn(f"warning: no audio files inside {path}{hint}")
            files.extend(found)
        elif path.is_file():
            if path.suffix.lower() not in extensions:
                _warn(f"warning: skipping unsupported file type: {path}")
                problems += 1
            else:
                files.append(path)
        else:
            _warn(f"warning: input not found: {path}")
            problems += 1
    seen: set[Path] = set()
    unique: list[Path] = []
    for path in sorted(files, key=lambda p: (p.stat().st_mtime, p.name)):
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique, problems


def _build_transcriber(config: Config) -> FallbackTranscriber:
    primary = None
    if config.asr_command:
        primary = CommandTranscriber(config.asr_command, timeout=config.asr_timeout)
    secondary = None
    if not config.offline:
        secondary = EndpointTranscriber(
            config.base_url,
            model=config.transcribe_model,
            timeout=config.asr_timeout,
        )
    return FallbackTranscriber(primary, secondary)


def _build_summarizer(config: Config) -> SummaryChain:
    endpoint = None
    if not config.offline:
        endpoint = EndpointSummarizer(
            config.base_url,
            model=config.llm_model,
            timeout=config.chat_timeout,
            max_chars=config.llm_max_chars,
        )
    return SummaryChain(endpoint)


def cmd_process(args) -> int:
    try:
        config, used_files = load_config(_overrides(args), args.config)
    except ConfigError as exc:
        _warn(f"config error: {exc}")
        return 2

    if not args.inputs:
        _warn("no input files given (try: vnt process recording.m4a)")
        return 2

    files, problems = _collect_inputs(args.inputs, config.audio_extensions, args.recursive)
    if not files:
        _warn("nothing to process: no supported audio files in the given inputs")
        return 2

    for path in used_files:
        if args.config is None or path != args.config:
            _line(f"using config: {path}")

    transcriber = _build_transcriber(config)
    summarizer = _build_summarizer(config)
    notes_dir = Path(config.notes_dir).expanduser()

    written: list[Path] = []
    failures: list[tuple[Path, str]] = []
    total = len(files)
    for index, audio in enumerate(files, 1):
        _line(f"[{index}/{total}] {audio.name}")
        try:
            note_date = _resolve_note_date(args.date, audio)
            transcript = transcriber.transcribe(audio)
            used_name = transcriber.used.name if transcriber.used is not None else "none"
            title, summary, summarizer_name = summarizer.summarize(transcript, audio.name)
            if args.dry_run:
                _line(f"  [dry-run] title: {title}")
                _line(f"  [dry-run] summary: {summary}")
                _line(f"  [dry-run] would file under: {notes_dir / f'{note_date:%Y}' / f'{note_date:%m}'}")
                continue
            out_path = write_note(
                notes_dir,
                title=title,
                summary=summary,
                transcript=transcript,
                note_date=note_date,
                source_name=audio.name,
                transcriber=used_name,
                summarizer=summarizer_name,
            )
            _line(f"  title:     {title}")
            _line(f"  summary:   {summary}")
            _line(f"  transcriber: {used_name}; summarizer: {summarizer_name}")
            _line(f"  wrote:     {out_path}")
            written.append(out_path)
        except (TranscribeError, NoteError, ConfigError) as exc:
            _warn(f"  failed: {exc}")
            failures.append((audio, str(exc)))

    _line(f"done: {len(written)} note(s) written, {len(failures)} failed")
    if failures:
        for audio, message in failures:
            _warn(f"failed: {audio.name}: {message}")
        return 1
    return 0


def cmd_search(args) -> int:
    try:
        config, _ = load_config(_overrides(args), args.config)
    except ConfigError as exc:
        _warn(f"config error: {exc}")
        return 2
    notes_dir = Path(config.notes_dir).expanduser()
    if not notes_dir.is_dir():
        _warn(f"no notes directory at {notes_dir} (process some audio first)")
        return 2
    results = search_notes(notes_dir, args.query)
    for path, number, line in results:
        _line(f"{path}:{number}: {line}")
    if not results:
        _warn(f"no matches for {args.query!r} in {notes_dir}")
        return 1
    matched_files = {path for path, _, _ in results}
    _line(f"found {len(results)} match(es) in {len(matched_files)} note(s)")
    return 0


def main(argv: list[str] | None = None) -> int:
    raw_argv = list(sys.argv[1:] if argv is None else argv)
    if raw_argv and raw_argv[0] not in SUBCOMMANDS and not raw_argv[0].startswith("-"):
        raw_argv = ["process", *raw_argv]
    parser = build_parser()
    args = parser.parse_args(raw_argv)
    if args.command is None:
        parser.print_help()
        return 2
    handlers = {
        "process": cmd_process,
        "init": cmd_init,
        "search": cmd_search,
        "doctor": cmd_doctor,
    }
    try:
        return handlers[args.command](args)
    except KeyboardInterrupt:
        _warn("interrupted")
        return 130
