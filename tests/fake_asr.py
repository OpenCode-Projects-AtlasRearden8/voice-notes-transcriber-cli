#!/usr/bin/env python3
"""A fake local ASR command used by the pytest suite.

Behavior: reads a sidecar file ``<input path>.expected.txt`` if it exists
and prints its contents; otherwise prints a generic fake transcript.
Usage:  fake_asr.py <audio-file>
"""
import pathlib
import sys


def main() -> int:
    if len(sys.argv) < 2:
        print("fake_asr.py: no input given", file=sys.stderr)
        return 2
    input_path = pathlib.Path(sys.argv[1])
    sidecar = input_path.with_name(input_path.name + ".expected.txt")
    if sidecar.exists():
        sys.stdout.write(sidecar.read_text(encoding="utf-8"))
    else:
        sys.stdout.write(f"FAKE TRANSCRIPT OF {input_path.name}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
