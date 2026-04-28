"""Finalized identity transition engine scaffolding."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from .actions import IdentityAction, IdentityActionValidator
from .models import IdentityState, RecoveryPolicyState
from .state import IdentityStateStore


@dataclass
class TransitionResult:
    """Result of applying one finalized identity action."""

    identity_id: str
    action_id: str
    updated: bool
    applied_effects: List[str] = field(default_factory=list)


class IdentityTransitionEngine:
    """Apply finalized identity actions into hot identity state."""

    def __init__(
        self,
        state_store: IdentityStateStore | None = None,
        validator: IdentityActionValidator | None = None,
    ) -> None:
        self.state_store = state_store or IdentityStateStore()
        self.validator = validator or IdentityActionValidator()

    def register_identity(
        self,
        identity_id: str,
        action_keys: list[str],
        guardian_keys: list[str] | None = None,
        recovery_threshold: int = 0,
        recovery_delay_epochs: int = 0,
    ) -> IdentityState:
        state = IdentityState(
            identity_id=identity_id,
            active_action_keys=list(action_keys),
            active_producer_keys=list(action_keys),
            recovery_policy=RecoveryPolicyState(),
        )
        state.recovery_policy.guardians = list(guardian_keys or [])
        state.recovery_policy.threshold = int(recovery_threshold)
        state.recovery_policy.delay_epochs = int(recovery_delay_epochs)
        self.state_store.put(state)
        return state

    def apply_finalized_action(self, action: IdentityAction, finalized_epoch: int) -> TransitionResult:
        state = self.state_store.require(action.identity_id)
        self.validator.validate_against_state(action, state)

        effects: List[str] = []
        if action.action_type in {"rotate_key", "rotate_spend_key"}:
            new_key = action.payload["new_key"]
            state.retired_action_keys.append(action.authorizing_key)
            if action.authorizing_key in state.active_action_keys:
                state.active_action_keys.remove(action.authorizing_key)
            if new_key not in state.active_action_keys:
                state.active_action_keys.append(new_key)
            if action.authorizing_key in state.active_producer_keys:
                state.active_producer_keys.remove(action.authorizing_key)
            if new_key not in state.active_producer_keys:
                state.active_producer_keys.append(new_key)
            state.key_version += 1
            effects.append("rotated-action-key")
        elif action.action_type == "start_recovery":
            pending = dict(action.payload)
            pending.setdefault(
                "pending_recovery_id",
                f"{state.identity_id}:{action.action_id}:recovery",
            )
            pending.setdefault(
                "delay_until",
                action.timestamp + state.recovery_policy.delay_epochs,
            )
            pending.setdefault("policy_version", state.recovery_policy.policy_version)
            state.pending_recovery = pending
            effects.append("started-recovery")
        elif action.action_type == "finalize_recovery":
            recovery_key = action.payload.get("new_key") or action.payload.get("proposed_new_key")
            state.pending_recovery = None
            state.active_action_keys = [recovery_key]
            state.active_producer_keys = [recovery_key]
            state.key_version += 1
            effects.append("finalized-recovery")
        elif action.action_type == "cancel_recovery":
            state.pending_recovery = None
            effects.append("cancelled-recovery")
        elif action.action_type == "delegate_producer":
            state.delegated_producer = action.payload["producer_id"]
            effects.append("delegated-producer")
        elif action.action_type == "revoke_delegate":
            state.delegated_producer = None
            effects.append("revoked-producer")
        elif action.action_type == "ack_penalty":
            state.phase = "probation"
            state.penalty_until_epoch = None
            effects.append("acknowledged-penalty")
        else:
            effects.append(action.action_type)

        state.trajectory_head = action.action_id
        state.sequence = action.sequence
        state.last_finalized_epoch = finalized_epoch
        self.state_store.put(state)
        return TransitionResult(
            identity_id=state.identity_id,
            action_id=action.action_id,
            updated=True,
            applied_effects=effects,
        )
