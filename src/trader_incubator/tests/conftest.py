from __future__ import annotations

import sys
import types
from pathlib import Path

_core_path = Path(__file__).parent.parent / "core"

# Create a fake top-level `trader_incubator` package that delegates attribute
# lookups to the actual modules inside core/.
if "trader_incubator" not in sys.modules:
    pkg = types.ModuleType("trader_incubator")
    pkg.__path__ = [str(_core_path)]  # type: ignore[assignment]
    pkg.__package__ = "trader_incubator"
    pkg.__spec__ = None  # type: ignore[assignment]
    sys.modules["trader_incubator"] = pkg
