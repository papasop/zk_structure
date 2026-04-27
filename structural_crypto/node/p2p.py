"""Minimal P2P and gossip datatypes for future multi-node testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class PeerInfo:
    node_id: str
    endpoint: str
    role: str = "full"


@dataclass(frozen=True)
class GossipEnvelope:
    kind: str
    origin: str
    payload: Dict[str, Any]
    ttl: int = 8
    metadata: Dict[str, Any] = field(default_factory=dict)

    def forward(self, next_hop: str) -> "GossipEnvelope":
        next_ttl = max(self.ttl - 1, 0)
        next_metadata = dict(self.metadata)
        next_metadata["forwarded_by"] = next_hop
        return GossipEnvelope(
            kind=self.kind,
            origin=self.origin,
            payload=dict(self.payload),
            ttl=next_ttl,
            metadata=next_metadata,
        )
