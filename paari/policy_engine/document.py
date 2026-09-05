"""Load policy documents from JSON files."""

from __future__ import annotations

import json
from pathlib import Path

from paari.schemas.policy import PolicyDocument, PolicyLayer

# The PAARI policy layer lives alongside the governance document (which is
# the constitution source, not a PolicyDocument). The layered policy files
# used by the policy engine are: paari_policy.json, merchant_demo.json,
# store_demo.json.
_DATA_DIR = Path(__file__).resolve().parents[1] / "governance" / "data"

_POLICY_FILES: dict[PolicyLayer, str] = {
    PolicyLayer.PAARI: "paari_policy.json",
    PolicyLayer.MERCHANT: "merchant_demo.json",
    PolicyLayer.STORE: "store_demo.json",
}


def load_policy_document(filename: str) -> PolicyDocument:
    """Load and validate a policy document from the data directory."""
    raw = json.loads((_DATA_DIR / filename).read_text(encoding="utf-8"))
    return PolicyDocument.model_validate(raw)


def load_policy_documents() -> dict[PolicyLayer, PolicyDocument]:
    """Load all layered policy documents (PAARI, MERCHANT, STORE)."""
    return {layer: load_policy_document(filename) for layer, filename in _POLICY_FILES.items()}
