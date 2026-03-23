from __future__ import annotations

import sys
from pathlib import Path

_core_path = Path(__file__).resolve().parents[1]
_src_path = Path(__file__).resolve().parents[3]

if str(_core_path) not in sys.path:
    sys.path.insert(0, str(_core_path))
if str(_src_path) not in sys.path:
    sys.path.insert(0, str(_src_path))

