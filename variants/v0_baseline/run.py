#!/usr/bin/env python3
"""Run V0 baseline on the Pi.

The implementation lives in pi/v0_baseline.py so the four variants can share the
common modules. This file exists so each variant folder is a working entry
point on its own.

    python3 variants/v0_baseline/run.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi"))

from v0_baseline import main

if __name__ == "__main__":
    main()
