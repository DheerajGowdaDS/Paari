"""Policy compiler: merges PAARI + MERCHANT + STORE + TX into one effective policy.

The effective policy is the ordered concatenation of layers. Evaluation is
monotonic: the first DENY wins; a REVIEW is a sticky escalation that later
layers cannot downgrade (but a later DENY still overrides it). This is enforced
in the engine, not here — this module only produces the ordered rule list.
"""

from __future__ import annotations

from dataclasses import dataclass

from paari.schemas.policy import PolicyDocument, PolicyLayer, PolicyRule


@dataclass(frozen=True)
class CompiledPolicy:
    """An ordered, versioned list of rules across all layers."""

    layers: list[PolicyLayer]
    documents: list[PolicyDocument]
    version: str  # e.g. "paari-v1+merchant-v1+store-v1"

    @property
    def rules(self) -> list[tuple[PolicyLayer, PolicyRule]]:
        """Flatten all layers into (layer, rule) pairs, in evaluation order."""
        out: list[tuple[PolicyLayer, PolicyRule]] = []
        for layer, doc in zip(self.layers, self.documents):
            for rule in doc.rules:
                out.append((layer, rule))
        return out


def compile_policy(
    paari: PolicyDocument,
    merchant: PolicyDocument,
    store: PolicyDocument,
    tx: PolicyDocument | None = None,
) -> CompiledPolicy:
    """Compile the four policy layers into one effective policy.

    Order matters: PAARI first (platform floor), then merchant, then store,
    then transaction context. More restrictive layers later can escalate but
    cannot weaken earlier mandatory rules.
    """
    layers = [PolicyLayer.PAARI, PolicyLayer.MERCHANT, PolicyLayer.STORE]
    docs = [paari, merchant, store]
    if tx is not None:
        layers.append(PolicyLayer.TX)
        docs.append(tx)
    version = "+".join(f"{d.layer.value.lower()}={d.version}" for d in docs)
    return CompiledPolicy(layers=layers, documents=docs, version=version)
