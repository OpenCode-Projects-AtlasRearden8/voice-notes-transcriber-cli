"""Allow `python -m vnt` directly from a source checkout."""

import sys

from vnt.cli import main

if __name__ == "__main__":
    sys.exit(main())
