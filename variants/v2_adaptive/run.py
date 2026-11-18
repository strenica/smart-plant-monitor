#!/usr/bin/env python3
"""Run V2 adaptive sampling on the Pi.

The implementation lives in pi/v2_adaptive.py so the four variants can share the
common modules. This file exists so each variant folder is a working entry
point on its own.

    python3 variants/v2_adaptive/run.py
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "pi"))

from v2_adaptive import main

if __name__ == "__main__":
    main()
