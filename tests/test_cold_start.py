"""Tests for the PoCT cold-start model."""

from __future__ import annotations

import unittest

from structural_crypto.consensus import BootstrapCredential, ColdStartEngine


class ColdStartTests(unittest.TestCase):
    def test_new_identity_starts_with_low_influence(self) -> None:
        engine = ColdStartEngine()
        state = engine.register_identity("alice")
        self.assertEqual(state.phase, "new")
        self.assertFalse(engine.can_participate_in_ordering(state))

    def test_history_growth_unlocks_ordering(self) -> None:
        engine = ColdStartEngine()
        state = engine.register_identity("alice")
        for _ in range(6):
            engine.record_compliant_tx(state, delta=0.2)
        self.assertEqual(state.phase, "probation")
        self.assertTrue(engine.can_participate_in_ordering(state))

    def test_external_boost_is_capped(self) -> None:
        engine = ColdStartEngine()
        state = engine.register_identity(
            "alice",
            credentials=[
                BootstrapCredential(source="world_id", score=0.2),
                BootstrapCredential(source="eth_history", score=0.5),
            ],
        )
        self.assertLessEqual(state.external_credential_score, engine.config.external_boost_cap)

    def test_branch_conflicts_hurt_maturation(self) -> None:
        engine = ColdStartEngine()
        state = engine.register_identity("alice")
        for _ in range(20):
            engine.record_compliant_tx(state, delta=0.1)
        engine.record_rejected_tx(state, branch_conflict=True)
        self.assertNotEqual(engine.phase_for(state), "mature")


if __name__ == "__main__":
    unittest.main()
