"""Tests for the identity-first state machine scaffolding."""

from __future__ import annotations

import unittest

from structural_crypto.identity import (
    IdentityAction,
    IdentityActionValidator,
    IdentityState,
    IdentityStateStore,
    IdentityTransitionEngine,
)


class IdentityTests(unittest.TestCase):
    def test_state_store_exports_stable_state_root(self) -> None:
        store = IdentityStateStore()
        store.put(IdentityState(identity_id="alice", active_action_keys=["alice-key"]))
        store.put(IdentityState(identity_id="bob", active_action_keys=["bob-key"]))

        root_a = store.state_root()
        root_b = store.state_root()

        self.assertEqual(root_a, root_b)
        self.assertEqual(store.export_state()["identity_count"], 2)

    def test_action_validator_rejects_wrong_sequence(self) -> None:
        validator = IdentityActionValidator()
        state = IdentityState(
            identity_id="alice",
            active_action_keys=["alice-key"],
            trajectory_head="act-0",
            sequence=0,
        )
        action = IdentityAction(
            action_id="act-2",
            identity_id="alice",
            action_type="delegate_producer",
            prev_action_id="act-0",
            sequence=2,
            timestamp=1,
            authorizing_key="alice-key",
            payload={"producer_id": "producer-1"},
        )

        with self.assertRaises(ValueError):
            validator.validate_against_state(action, state)

    def test_action_validator_rejects_unauthorized_key(self) -> None:
        validator = IdentityActionValidator()
        state = IdentityState(
            identity_id="alice",
            active_action_keys=["alice-key"],
            trajectory_head=None,
            sequence=-1,
        )
        action = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="delegate_producer",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="mallory-key",
            payload={"producer_id": "producer-1"},
        )

        with self.assertRaises(ValueError):
            validator.validate_against_state(action, state)

    def test_transition_engine_registers_identity(self) -> None:
        engine = IdentityTransitionEngine()

        state = engine.register_identity("alice", ["alice-key"])

        self.assertEqual(state.identity_id, "alice")
        self.assertEqual(state.active_action_keys, ["alice-key"])
        self.assertEqual(engine.state_store.require("alice").identity_id, "alice")

    def test_transition_engine_applies_delegate_producer_action(self) -> None:
        engine = IdentityTransitionEngine()
        engine.register_identity("alice", ["alice-key"])
        action = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="delegate_producer",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="alice-key",
            payload={"producer_id": "producer-1"},
        )

        result = engine.apply_finalized_action(action, finalized_epoch=7)
        state = engine.state_store.require("alice")

        self.assertTrue(result.updated)
        self.assertIn("delegated-producer", result.applied_effects)
        self.assertEqual(state.delegated_producer, "producer-1")
        self.assertEqual(state.trajectory_head, "act-1")
        self.assertEqual(state.sequence, 0)
        self.assertEqual(state.last_finalized_epoch, 7)

    def test_transition_engine_applies_rotate_key_action(self) -> None:
        engine = IdentityTransitionEngine()
        engine.register_identity("alice", ["alice-key"])
        action = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="rotate_key",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="alice-key",
            payload={"new_key": "alice-key-2"},
        )

        result = engine.apply_finalized_action(action, finalized_epoch=2)
        state = engine.state_store.require("alice")

        self.assertIn("rotated-action-key", result.applied_effects)
        self.assertEqual(state.active_action_keys, ["alice-key-2"])
        self.assertIn("alice-key", state.retired_action_keys)

    def test_transition_engine_starts_and_finalizes_recovery(self) -> None:
        engine = IdentityTransitionEngine()
        engine.register_identity(
            "alice",
            ["alice-key"],
            guardian_keys=["g1", "g2", "g3"],
            recovery_threshold=2,
            recovery_delay_epochs=2,
        )

        start = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="start_recovery",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="alice-key",
            payload={
                "new_key": "alice-recovery-key",
                "approvals": [{"guardian": "g1"}, {"guardian": "g2"}],
                "recovery_policy_version": 1,
            },
        )
        engine.apply_finalized_action(start, finalized_epoch=3)
        state_after_start = engine.state_store.require("alice")
        self.assertIsNotNone(state_after_start.pending_recovery)
        self.assertEqual(state_after_start.pending_recovery["delay_until"], 3)

        finalize = IdentityAction(
            action_id="act-2",
            identity_id="alice",
            action_type="finalize_recovery",
            prev_action_id="act-1",
            sequence=1,
            timestamp=3,
            authorizing_key="alice-key",
            payload={
                "new_key": "alice-recovery-key",
                "pending_recovery_id": state_after_start.pending_recovery["pending_recovery_id"],
            },
        )
        engine.apply_finalized_action(finalize, finalized_epoch=4)
        state_after_finalize = engine.state_store.require("alice")

        self.assertIsNone(state_after_finalize.pending_recovery)
        self.assertEqual(state_after_finalize.active_action_keys, ["alice-recovery-key"])

    def test_recovery_requires_threshold_and_delay(self) -> None:
        engine = IdentityTransitionEngine()
        engine.register_identity(
            "alice",
            ["alice-key"],
            guardian_keys=["g1", "g2", "g3"],
            recovery_threshold=2,
            recovery_delay_epochs=5,
        )
        start = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="start_recovery",
            prev_action_id=None,
            sequence=0,
            timestamp=10,
            authorizing_key="alice-key",
            payload={
                "new_key": "alice-recovery-key",
                "approvals": [{"guardian": "g1"}],
                "recovery_policy_version": 1,
            },
        )

        with self.assertRaises(ValueError):
            engine.apply_finalized_action(start, finalized_epoch=10)

    def test_transition_engine_revokes_delegate(self) -> None:
        engine = IdentityTransitionEngine()
        engine.register_identity("alice", ["alice-key"])

        delegate = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="delegate_producer",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="alice-key",
            payload={"producer_id": "producer-1"},
        )
        revoke = IdentityAction(
            action_id="act-2",
            identity_id="alice",
            action_type="revoke_delegate",
            prev_action_id="act-1",
            sequence=1,
            timestamp=2,
            authorizing_key="alice-key",
            payload={},
        )

        engine.apply_finalized_action(delegate, finalized_epoch=1)
        engine.apply_finalized_action(revoke, finalized_epoch=2)
        state = engine.state_store.require("alice")

        self.assertIsNone(state.delegated_producer)

    def test_transition_engine_acknowledges_penalty(self) -> None:
        engine = IdentityTransitionEngine()
        state = engine.register_identity("alice", ["alice-key"])
        state.phase = "penalized"
        state.penalty_until_epoch = 10
        engine.state_store.put(state)

        action = IdentityAction(
            action_id="act-1",
            identity_id="alice",
            action_type="ack_penalty",
            prev_action_id=None,
            sequence=0,
            timestamp=1,
            authorizing_key="alice-key",
            payload={},
        )

        engine.apply_finalized_action(action, finalized_epoch=11)
        restored = engine.state_store.require("alice")

        self.assertEqual(restored.phase, "probation")
        self.assertIsNone(restored.penalty_until_epoch)


if __name__ == "__main__":
    unittest.main()
