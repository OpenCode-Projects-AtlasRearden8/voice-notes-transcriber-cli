import shlex
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
TESTS_DIR = Path(__file__).resolve().parent
for path_entry in (str(SRC), str(TESTS_DIR)):
    if path_entry not in sys.path:
        sys.path.insert(0, path_entry)

from vnt.cli import main as cli_main  # noqa: E402


def make_asr_command() -> str:
    """Return an ASR command string backed by tests/fake_asr.py.

    The fake ASR reads a sidecar text file named ``<audio>.expected.txt``
    when present, otherwise prints a generic fake transcript.
    """
    fake_asr = TESTS_DIR / "fake_asr.py"
    return f"{shlex.quote(sys.executable)} {shlex.quote(str(fake_asr))} {{input}}"


@pytest.fixture
def run_cli():
    def _run(argv):
        return cli_main([str(arg) for arg in argv])

    return _run


@pytest.fixture
def server():
    from fake_server import FakeEndpointServer

    with FakeEndpointServer() as srv:
        yield srv
