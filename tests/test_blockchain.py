"""Tests for the minimal blockchain prototype."""

from __future__ import annotations

import unittest

from structural_crypto.app.demo import run_demo
from structural_crypto.crypto.policy import PolicyCommitment, PolicyError
from structural_crypto.ledger.blockchain import Blockchain, ValidationError
from structural_crypto.node.wallet import Wallet


class BlockchainTests(unittest.TestCase):
    def test_demo_runs_and_chain_is_valid(self) -> None:
        result = run_demo()
        self.assertTrue(result["valid"])
        self.assertEqual(result["block_index"], 1)
        self.assertGreater(len(result["balances"]), 0)

    def test_policy_rejects_invalid_recipient(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        mallory = Wallet("mallory", "mallory-seed")
        chain.faucet(alice.address, 50)

        policy = PolicyCommitment.from_values(
            epsilon=3.0,
            max_amount=20,
            allowed_recipients=[bob.address],
        )
        with self.assertRaises(PolicyError):
            chain.build_transaction(
                key=alice.key,
                recipients=[(mallory.address, 10)],
                policy=policy,
            )

    def test_insufficient_balance_is_rejected(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 10)
        policy = PolicyCommitment.from_values(epsilon=3.0, max_amount=50)
        with self.assertRaises(ValidationError):
            chain.build_transaction(
                key=alice.key,
                recipients=[(bob.address, 20)],
                policy=policy,
            )


if __name__ == "__main__":
    unittest.main()
