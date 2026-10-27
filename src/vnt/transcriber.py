"""Transcription backends: local ASR command with endpoint fallback."""

from __future__ import annotations

import json
import mimetypes
import shlex
import subprocess
import sys
from pathlib import Path

from vnt import client


class TranscribeError(Exception):
    """Raised when a transcription backend fails."""


class Transcriber:
    name: str = "unknown"

    def transcribe(self, path: Path) -> str:
        raise NotImplementedError


class CommandTranscriber(Transcriber):
    """Runs a configurable local ASR command (e.g. whisper.cpp/whisper-cli).

    The command template must contain ``{input}``, which is replaced by the
    audio file path. The command must print the transcript text to stdout.
    """

    def __init__(self, template: str, timeout: float = 600.0):
        self.template = template
        self.timeout = timeout
        try:
            self.tokens = shlex.split(template)
        except ValueError as exc:
            raise TranscribeError(f"cannot parse asr_command {template!r}: {exc}") from exc
        if not self.tokens:
            raise TranscribeError("asr_command is empty")
        if not any("{input}" in token for token in self.tokens):
            raise TranscribeError(
                "asr_command must contain '{input}' where the audio file goes"
            )

    @property
    def name(self) -> str:
        first = Path(self.tokens[0]).name
        if first.startswith("python"):
            for token in self.tokens[1:]:
                if token.endswith(".py"):
                    return Path(token).name
        return first

    def transcribe(self, path: Path) -> str:
        argv = [token.replace("{input}", str(path)) for token in self.tokens]
        try:
            proc = subprocess.run(
                argv, capture_output=True, text=True, timeout=self.timeout
            )
        except FileNotFoundError as exc:
            raise TranscribeError(
                f"asr_command not found: {self.tokens[0]!r} ({exc})"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise TranscribeError(
                f"asr_command timed out after {self.timeout}s"
            ) from exc
        if proc.returncode != 0:
            stderr = (proc.stderr or "").strip()
            raise TranscribeError(
                f"asr_command exited with code {proc.returncode}"
                + (f": {stderr[:300]}" if stderr else "")
            )
        text = proc.stdout.strip()
        if not text:
            raise TranscribeError("asr_command produced no transcript output")
        return text


class EndpointTranscriber(Transcriber):
    """Fallback transcription via an OpenAI-compatible endpoint.

    POSTs the audio file as multipart/form-data to ``{base_url}/audio/transcriptions``
    (for example, a whisper-serving OpenAI-compatible server). No API keys
    are ever sent.
    """

    def __init__(self, base_url: str, model: str | None = None,
                 timeout: float = 600.0):
        self.base_url = base_url.rstrip("/")
        self._explicit_model = model
        self.timeout = timeout
        self._cached_model: str | None = None

    @property
    def name(self) -> str:
        return f"endpoint:{self._model_hint()}"

    def _model_hint(self) -> str:
        return self._cached_model or self._explicit_model or "auto"

    def _model(self) -> str:
        if self._cached_model:
            return self._cached_model
        if self._explicit_model:
            self._cached_model = self._explicit_model
            return self._cached_model
        # Ask the server which models it has; prefer a whisper-ish one.
        status, body = client.get_json(
            f"{self.base_url}/models", timeout=min(self.timeout, 15.0)
        )
        if status == 200:
            try:
                ids = [str(item["id"]) for item in json.loads(body).get("data", [])]
            except (ValueError, KeyError, TypeError):
                ids = []
            if ids:
                self._cached_model = next(
                    (i for i in ids if "whisper" in i.lower()), ids[0]
                )
                return self._cached_model
        self._cached_model = "whisper-1"
        return self._cached_model

    def transcribe(self, path: Path) -> str:
        try:
            model = self._model()
        except client.ClientError as exc:
            raise TranscribeError(f"endpoint transcription failed: {exc}") from exc
        url = f"{self.base_url}/audio/transcriptions"
        mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        try:
            status, body = client.post_multipart(
                url,
                fields={"model": model},
                filename=path.name,
                content=path.read_bytes(),
                content_type=mime,
                timeout=self.timeout,
            )
        except (client.ClientError, OSError) as exc:
            raise TranscribeError(f"endpoint transcription failed: {exc}") from exc
        if status != 200:
            raise TranscribeError(
                f"endpoint transcription failed: HTTP {status}: "
                f"{body[:200].decode('utf-8', 'replace')}"
            )
        try:
            data = json.loads(body)
            text = data.get("text") if isinstance(data, dict) else None
        except ValueError:
            text = None
        if text is None:
            text = body.decode("utf-8", "replace")
        text = text.strip()
        if not text:
            raise TranscribeError("endpoint returned an empty transcription")
        return text


class FallbackTranscriber(Transcriber):
    """Tries the local ASR command first, then the endpoint fallback."""

    def __init__(self, primary: Transcriber | None, secondary: Transcriber | None):
        self.primary = primary
        self.secondary = secondary
        self.used: Transcriber | None = None

    @property
    def name(self) -> str:
        return self.used.name if self.used is not None else "none"

    def transcribe(self, path: Path) -> str:
        errors: list[str] = []
        for transcriber in (self.primary, self.secondary):
            if transcriber is None:
                continue
            try:
                text = transcriber.transcribe(path)
            except TranscribeError as exc:
                errors.append(f"[{transcriber.name}] {exc}")
                print(
                    f"note: transcriber {transcriber.name} failed ({exc}); trying next",
                    file=sys.stderr,
                )
                continue
            self.used = transcriber
            return text
        detail = "; ".join(errors) if errors else "no transcriber configured"
        raise TranscribeError(f"all transcription options failed: {detail}")
