"""Test configuration: force stub mode for all tests.

The .env may have PAARI_SHOPIFY_MODE=live for production testing, but the
test suite always runs against stub fixtures to stay fast and offline.
"""

from __future__ import annotations

import os

# Force stub mode before any Paari module imports
os.environ["PAARI_SHOPIFY_MODE"] = "stub"

# Clear cached settings so the new env var takes effect
import paari.config  # noqa: E402

paari.config.settings = paari.config.Settings()

# Reload the tool registry with stub mode
import paari.tools.registry as _reg  # noqa: E402

_reg.REGISTRY = _reg.build_registry()
