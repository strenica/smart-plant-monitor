#!/usr/bin/env python3
"""Run the final build on the Pi.

One photograph per wake, then halt. The implementation lives in pi/v3_wake.py
so every variant shares the common modules; this file exists so the folder is a
working entry point on its own.

    python3 variants/final/run.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi"))

from v3_wake import main

if __name__ == "__main__":
    main()
