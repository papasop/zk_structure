"""Core identity-first state objects."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RecoveryPolicyState:
    """Recovery configuration attached to one identity."""

    guardians: List[str] = field(default_factory=list)
    threshold: int = 0
    delay_epochs: int = 0
    policy_version: int = 1


@dataclass
class IdentityState:
    """Minimal hot identity state for finalized execution."""

    identity_id: str
    active_action_keys: List[str] = field(default_factory=list)
    active_producer_keys: List[str] = field(default_factory=list)
    retired_action_keys: List[str] = field(default_factory=list)
    recovery_policy: RecoveryPolicyState = field(default_factory=RecoveryPolicyState)
    pending_recovery: Optional[Dict[str, Any]] = None
    key_version: int = 0

    trajectory_head: Optional[str] = None
    sequence: int = -1

    phase: str = "new"
    ordering_score: float = 0.0
    equivocation_count: int = 0
    penalty_until_epoch: Optional[int] = None

    delegated_producer: Optional[str] = None
    last_finalized_epoch: int = 0

    def action_key_is_active(self, action_key: str) -> bool:
        return action_key in self.active_action_keys

    def is_penalized(self, epoch: int | None = None) -> bool:
        if self.phase != "penalized":
            return False
        if epoch is None or self.penalty_until_epoch is None:
            return True
        return epoch <= self.penalty_until_epoch


@dataclass(frozen=True)
class IdentitySnapshot:
    """Snapshot metadata for finalized identity world state."""

    checkpoint_id: str
    state_root: str
    identity_count: int
    created_at: int
    storage_ref: str


@dataclass(frozen=True)
class EquivocationEvidence:
    """Recorded evidence for conflicting identity behavior."""

    identity_id: str
    evidence_type: str
    epoch: int
    round: Optional[int]
    object_a_digest: str
    object_b_digest: str
    recorded_at: int
