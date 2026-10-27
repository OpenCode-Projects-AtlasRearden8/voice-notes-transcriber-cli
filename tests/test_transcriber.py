import sys
from pathlib import Path

import pytest

from vnt.transcriber import (
    CommandTranscriber,
    EndpointTranscriber,
    FallbackTranscriber,
    TranscribeError,
)


class StubTranscriber:
    def __init__(self, name, behavior):
        self._name = name
        self._behavior = behavior
        self.calls = 0

    @property
    def name(self):
        return self._name

    def transcribe(self, path):
        self.calls += 1
        if isinstance(self._behavior, Exception):
            raise self._behavior
        return self._behavior


def test_command_transcriber_uses_sidecar(tmp_path):
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"x")
    (tmp_path / "memo.m4a.expected.txt").write_text("sidecar transcript\n", encoding="utf-8")
    cmd = CommandTranscriber(f"{sys.executable} {Path(__file__).parent / 'fake_asr.py'} {{input}}")
    assert cmd.name == "fake_asr.py"
    assert cmd.transcribe(audio) == "sidecar transcript"


def test_command_transcriber_failing_command(tmp_path):
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"x")
    cmd = CommandTranscriber(f'{sys.executable} -c "import sys; sys.exit(3)" {{input}}')
    with pytest.raises(TranscribeError, match="code 3"):
        cmd.transcribe(audio)


def test_command_transcriber_missing_placeholder():
    with pytest.raises(TranscribeError, match="\\{input\\}"):
        CommandTranscriber("echo hi")


def test_command_transcriber_not_found(tmp_path):
    cmd = CommandTranscriber("no-such-binary-xyz {input}")
    with pytest.raises(TranscribeError, match="not found"):
        cmd.transcribe(tmp_path / "memo.m4a")


def test_endpoint_transcriber_round_trip(tmp_path, server):
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"audio-bytes")
    transcriber = EndpointTranscriber(server.base_url)
    assert transcriber.transcribe(audio) == "TRANSCRIPT FROM memo.m4a"
    assert transcriber.name == "endpoint:fake-whisper"


def test_endpoint_transcriber_server_error(tmp_path, server):
    server.fail_transcriptions = True
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"audio-bytes")
    transcriber = EndpointTranscriber(server.base_url)
    with pytest.raises(TranscribeError, match="HTTP 500"):
        transcriber.transcribe(audio)


def test_endpoint_transcriber_dead_endpoint(tmp_path):
    audio = tmp_path / "memo.m4a"
    audio.write_bytes(b"audio-bytes")
    transcriber = EndpointTranscriber("http://127.0.0.1:9/v1")
    with pytest.raises(TranscribeError):
        transcriber.transcribe(audio)


def test_fallback_prefers_local_command(tmp_path, server):
    good = StubTranscriber("good-asr", "local text")
    bad = StubTranscriber("bad-asr", TranscribeError("boom"))
    fallback = FallbackTranscriber(good, bad)
    assert fallback.transcribe(Path("memo.m4a")) == "local text"
    assert good.calls == 1 and bad.calls == 0
    assert fallback.name == "good-asr"


def test_fallback_uses_endpoint_when_local_fails(tmp_path):
    bad = StubTranscriber("bad-asr", TranscribeError("boom"))
    good = StubTranscriber("endpoint", "endpoint text")
    fallback = FallbackTranscriber(bad, good)
    assert fallback.transcribe(Path("memo.m4a")) == "endpoint text"
    assert bad.calls == 1 and good.calls == 1
    assert fallback.name == "endpoint"


def test_fallback_all_fail(tmp_path):
    bad1 = StubTranscriber("one", TranscribeError("boom1"))
    bad2 = StubTranscriber("two", TranscribeError("boom2"))
    fallback = FallbackTranscriber(bad1, bad2)
    with pytest.raises(TranscribeError, match="all transcription options failed"):
        fallback.transcribe(Path("memo.m4a"))


def test_fallback_with_no_backends(tmp_path):
    fallback = FallbackTranscriber(None, None)
    with pytest.raises(TranscribeError, match="no transcriber"):
        fallback.transcribe(Path("memo.m4a"))
