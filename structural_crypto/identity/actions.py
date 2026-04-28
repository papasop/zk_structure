"""Identity action grammar and stateless validation helpers."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from .models import IdentityState


ALLOWED_ACTION_TYPES = {
    "transfer",
    "rotate_key",
    "rotate_spend_key",
    "add_guardian",
    "remove_guardian",
    "start_recovery",
    "finalize_recovery",
    "cancel_recovery",
    "delegate_producer",
    "revoke_delegate",
    "ack_penalty",
}


@dataclass(frozen=True)
class IdentityAction:
    """One identity-scoped state transition request."""

    action_id: str
    identity_id: str
    action_type: str
    prev_action_id: Optional[str]
    sequence: int
    timestamp: int

    authorizing_key: str
    payload: Dict[str, Any] = field(default_factory=dict)
    policy_hash: Optional[str] = None
    signature: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class IdentityActionEnvelope:
    """Transport-friendly wrapper for future ordering / gossip layers."""

    action: IdentityAction
    source: str
    metadata: Dict[str, Any] = field(default_factory=dict)


class IdentityActionValidator:
    """Perform syntax and hot-state checks before finalized execution."""

    def validate_action_type(self, action: IdentityAction) -> None:
        if action.action_type not in ALLOWED_ACTION_TYPES:
            raise ValueError(f"unsupported identity action type: {action.action_type}")

    def validate_against_state(self, action: IdentityAction, state: IdentityState) -> None:
        self.validate_action_type(action)
        if action.identity_id != state.identity_id:
            raise ValueError("identity action does not match target identity state")
        if action.sequence != state.sequence + 1:
            raise ValueError("identity action sequence does not extend the current trajectory")
        if action.prev_action_id != state.trajectory_head:
            raise ValueError("identity action prev does not match the current trajectory head")
        self._validate_authority(action, state)
        self._validate_action_payload(action, state)

    def _validate_authority(self, action: IdentityAction, state: IdentityState) -> None:
        if action.action_type == "start_recovery":
            self._validate_recovery_approvals(action, state)
            return
        if action.action_type == "finalize_recovery":
            if state.pending_recovery is None:
                raise ValueError("cannot finalize recovery without a pending recovery")
            self._validate_recovery_approvals(action, state, allow_persisted=True)
            return
        if action.action_type == "cancel_recovery":
            if state.pending_recovery is None:
                raise ValueError("cannot cancel recovery when no pending recovery exists")
        if not state.action_key_is_active(action.authorizing_key):
            raise ValueError("identity action key is not currently authorized")

    def _validate_action_payload(self, action: IdentityAction, state: IdentityState) -> None:
        if action.action_type in {"rotate_key", "rotate_spend_key"}:
            new_key = str(action.payload.get("new_key", "")).strip()
            if not new_key:
                raise ValueError("rotate key action requires a non-empty new_key")
            if new_key == action.authorizing_key:
                raise ValueError("rotate key action must introduce a different key")
        elif action.action_type == "start_recovery":
            if state.pending_recovery is not None:
                raise ValueError("recovery is already pending for this identity")
            proposed_key = str(action.payload.get("new_key") or action.payload.get("proposed_new_key") or "").strip()
            if not proposed_key:
                raise ValueError("start recovery action requires a proposed new key")
            policy_version = int(action.payload.get("recovery_policy_version", state.recovery_policy.policy_version))
            if policy_version != state.recovery_policy.policy_version:
                raise ValueError("recovery action does not match the active recovery policy version")
        elif action.action_type == "finalize_recovery":
            pending = state.pending_recovery
            if pending is None:
                raise ValueError("cannot finalize recovery without a pending recovery")
            pending_id = action.payload.get("pending_recovery_id")
            if pending_id and pending_id != pending.get("pending_recovery_id"):
                raise ValueError("recovery finalization references the wrong pending recovery")
            expected_key = pending.get("new_key") or pending.get("proposed_new_key")
            supplied_key = action.payload.get("new_key") or action.payload.get("proposed_new_key")
            if expected_key != supplied_key:
                raise ValueError("recovery finalization must use the pending recovery key")
            if action.timestamp < int(pending.get("delay_until", 0)):
                raise ValueError("recovery delay has not elapsed")
        elif action.action_type == "cancel_recovery":
            pending = state.pending_recovery
            if pending is None:
                raise ValueError("cannot cancel recovery without a pending recovery")
            pending_id = action.payload.get("pending_recovery_id")
            if pending_id and pending_id != pending.get("pending_recovery_id"):
                raise ValueError("recovery cancellation references the wrong pending recovery")

    def _validate_recovery_approvals(
        self,
        action: IdentityAction,
        state: IdentityState,
        allow_persisted: bool = False,
    ) -> None:
        approvals = action.payload.get("approvals") or action.signature.get("approvals") or []
        if not approvals and allow_persisted and state.pending_recovery is not None:
            approvals = state.pending_recovery.get("approvals", [])
        guardians = set(state.recovery_policy.guardians)
        unique_approvers = {
            str(approval.get("guardian"))
            for approval in approvals
            if str(approval.get("guardian")) in guardians
        }
        if len(unique_approvers) < state.recovery_policy.threshold:
            raise ValueError("recovery action does not satisfy guardian threshold")
