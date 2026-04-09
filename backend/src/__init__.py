"""Wind energy forecasting package."""

from __future__ import annotations

import sys


# Backward-compatibility alias for older pickled artifacts saved under the old `src.*` module path.
sys.modules.setdefault("src", sys.modules[__name__])
