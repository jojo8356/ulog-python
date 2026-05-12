"""Allow `python -m ulog._cli ...` invocation (Story 3.7)."""

from __future__ import annotations

import sys

from . import main

if __name__ == "__main__":
    sys.exit(main())
