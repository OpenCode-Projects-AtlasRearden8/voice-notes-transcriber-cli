"""Note formatting and writing: notes/YYYY/MM/YYYY-MM-DD-slug.md."""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from pathlib import Path


class NoteError(Exception):
    """Raised when a note cannot be written."""


def slugify(text: str, max_len: int = 60) -> str:
    """Turn a title into a safe, lowercase, hyphenated filename slug."""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text.lower()).strip("-")
    if len(slug) > max_len:
        slug = slug[:max_len].rsplit("-", 1)[0]
    return slug or "voice-note"


def yaml_value(text: str) -> str:
    """Quote a string for single-line YAML front matter."""
    safe = " ".join(str(text).splitlines())
    return '"' + safe.replace("\\", "\\\\").replace('"', '\\"') + '"'


def build_note(
    *,
    title: str,
    summary: str,
    transcript: str,
    note_date: datetime,
    source_name: str,
    transcriber: str,
    summarizer: str,
) -> str:
    lines = [
        "---",
        f"title: {yaml_value(title)}",
        f"date: {yaml_value(note_date.strftime('%Y-%m-%d %H:%M'))}",
        f"summary: {yaml_value(summary)}",
        f"source: {yaml_value(source_name)}",
        f"transcriber: {yaml_value(transcriber)}",
        f"summarizer: {yaml_value(summarizer)}",
        "---",
        "",
        f"# {title}",
        "",
        summary,
        "",
        "## Transcript",
        "",
        transcript.strip(),
        "",
    ]
    return "\n".join(lines)


def write_note(
    notes_dir: Path,
    *,
    title: str,
    summary: str,
    transcript: str,
    note_date: datetime,
    source_name: str,
    transcriber: str,
    summarizer: str,
) -> Path:
    """Write one Markdown note, avoiding filename collisions (-2, -3, ...)."""
    folder = notes_dir / f"{note_date:%Y}" / f"{note_date:%m}"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise NoteError(f"cannot create note folder {folder}: {exc}") from exc
    base = f"{note_date:%Y-%m-%d}-{slugify(title)}"
    path = folder / f"{base}.md"
    counter = 2
    while path.exists():
        path = folder / f"{base}-{counter}.md"
        counter += 1
    content = build_note(
        title=title,
        summary=summary,
        transcript=transcript,
        note_date=note_date,
        source_name=source_name,
        transcriber=transcriber,
        summarizer=summarizer,
    )
    try:
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        raise NoteError(f"cannot write note {path}: {exc}") from exc
    return path


def search_notes(notes_dir: Path, query: str) -> list[tuple[Path, int, str]]:
    """Case-insensitive substring search across all note Markdown files."""
    needle = query.lower()
    results: list[tuple[Path, int, str]] = []
    for md in sorted(notes_dir.rglob("*.md")):
        try:
            lines = md.read_text(encoding="utf-8").splitlines()
        except OSError:
            continue
        for number, line in enumerate(lines, 1):
            if needle in line.lower():
                results.append((md, number, line.strip()))
    return results
