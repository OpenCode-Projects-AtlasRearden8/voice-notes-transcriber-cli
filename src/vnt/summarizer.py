"""Title + one-line summary generation.

Primary: an OpenAI-compatible chat endpoint (default Ollama at
http://localhost:11434/v1, keyless). Fallback: a purely local heuristic
so notes are still created when no endpoint is available.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from vnt import client

SYSTEM_PROMPT = (
    "You turn voice memo transcripts into short note metadata. "
    'Reply with ONLY a single-line JSON object, no code fences, no preamble, '
    'exactly: {"title": "<at most 6 words, Title Case, no trailing period>", '
    '"summary": "<one plain declarative sentence, under 140 characters>"}. '
    "No extra keys."
)


class SummarizeError(Exception):
    """Raised when endpoint summarization fails."""


class EndpointSummarizer:
    def __init__(self, base_url: str, model: str | None = None,
                 timeout: float = 120.0, max_chars: int = 8000):
        self.base_url = base_url.rstrip("/")
        self._explicit_model = model
        self.timeout = timeout
        self.max_chars = max_chars
        self._cached_model: str | None = None

    @property
    def name(self) -> str:
        return f"endpoint:{self._cached_model or self._explicit_model or 'auto'}"

    def _model(self) -> str:
        if self._cached_model:
            return self._cached_model
        if self._explicit_model:
            self._cached_model = self._explicit_model
            return self._cached_model
        status, body = client.get_json(
            f"{self.base_url}/models", timeout=min(self.timeout, 15.0)
        )
        if status == 200:
            try:
                ids = [str(item["id"]) for item in json.loads(body).get("data", [])]
            except (ValueError, KeyError, TypeError):
                ids = []
            if ids:
                self._cached_model = ids[0]
                return self._cached_model
        raise SummarizeError(
            "endpoint has no models listed; set llm_model in your config"
        )

    def summarize(self, transcript: str) -> tuple[str, str]:
        try:
            model = self._model()
        except client.ClientError as exc:
            raise SummarizeError(str(exc)) from exc
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": transcript[: self.max_chars]
                    + ("\n[transcript truncated]" if len(transcript) > self.max_chars else ""),
                },
            ],
            "temperature": 0.2,
            "stream": False,
        }
        try:
            status, body = client.post_json(
                f"{self.base_url}/chat/completions",
                payload,
                timeout=self.timeout,
            )
            if status != 200:
                raise SummarizeError(
                    f"HTTP {status}: {body[:200].decode('utf-8', 'replace')}"
                )
            data = json.loads(body)
            content = data["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                raise SummarizeError("malformed chat completion response")
        except (client.ClientError, SummarizeError) as exc:
            message = exc if isinstance(exc, SummarizeError) else str(exc)
            raise SummarizeError(str(message)) from exc
        except Exception as exc:  # malformed bodies, timeouts, etc.
            raise SummarizeError(str(exc)) from exc
        parsed = parse_reply(content)
        if parsed is None:
            raise SummarizeError(f"could not parse model reply: {content[:120]!r}")
        return parsed


def parse_reply(content: str) -> tuple[str, str] | None:
    """Extract (title, summary) from a model reply.

    Accepts clean JSON, fenced JSON, or a plain "Title: / Summary:" two-liner.
    """
    text = content.strip()
    fenced = re.match(r"^```[a-zA-Z]*\s*(.*?)\s*```$", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        try:
            data = json.loads(text[start : end + 1])
            title = str(data.get("title", "")).strip()
            summary = str(data.get("summary", "")).strip()
            if title or summary:
                return _clean(title) or "Voice note", _clean(summary)
        except ValueError:
            pass
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2:
        title = re.sub(r"^(title)\s*:\s*", "", lines[0], flags=re.IGNORECASE)
        summary = re.sub(r"^(summary)\s*:\s*", "", " ".join(lines[1:]), flags=re.IGNORECASE)
        return _clean(title) or "Voice note", _clean(summary)
    if lines:
        return _clean(lines[0]) or "Voice note", _clean(lines[0])
    return None


def _clean(value: str, *, max_title: int = 80, max_summary: int = 240) -> str:
    value = value.strip().strip('"').strip("'").strip()
    return value


def truncate_to_word(text: str, limit: int) -> str:
    """Trim to at most ``limit`` characters, cutting on a word boundary."""
    if len(text) <= limit:
        return text
    cut = text[: max(limit - 3, 1)].rsplit(" ", 1)[0] or text[: max(limit - 3, 1)]
    return cut.rstrip(",;: ") + "..."


def local_summary(transcript: str, source_name: str) -> tuple[str, str]:
    """Heuristic title/summary used when no endpoint is reachable."""
    text = " ".join(transcript.split())
    if not text:
        stem = Path(source_name).stem.replace("-", " ").replace("_", " ").strip()
        return (f"Voice note {stem}".strip() or "Voice note"), "(empty transcript)"
    sentence = re.match(r"^[^.!?]*[.!?]?", text)
    first_sentence = sentence.group(0).strip() if sentence else text
    if not first_sentence:
        first_sentence = text
    words = first_sentence.split()
    raw_title = " ".join(words[:6]).rstrip(".,!?;:")
    title = raw_title[:1].upper() + raw_title[1:] if raw_title else "Voice note"
    title = truncate_to_word(title, 60)
    summary = first_sentence
    summary = truncate_to_word(summary if summary.endswith((".", "!", "?")) else summary + ".", 160)
    return title, summary


class SummaryChain:
    """Tries the endpoint summarizer, falling back to local heuristics."""

    def __init__(self, endpoint: EndpointSummarizer | None):
        self.endpoint = endpoint
        self.used: str = "local-fallback"

    def summarize(self, transcript: str, source_name: str) -> tuple[str, str, str]:
        if self.endpoint is not None:
            try:
                title, summary = self.endpoint.summarize(transcript)
                self.used = self.endpoint.name
                return title or "Voice note", summary or "(no summary)", self.used
            except SummarizeError as exc:
                print(
                    f"note: endpoint summary failed ({exc}); using local fallback",
                    file=sys.stderr,
                )
        title, summary = local_summary(transcript, source_name)
        self.used = "local-fallback"
        return title, summary, self.used
