"""Tests for the minimal blockchain prototype."""

from __future__ import annotations

from dataclasses import replace
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
        self.assertGreater(len(result["trajectories"]), 0)

    def test_policy_rejects_invalid_recipient(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        mallory = Wallet("mallory", "mallory-seed")
        chain.faucet(alice.address, 50)

        policy = PolicyCommitment.from_values(
            epsilon=10.0,
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
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=50)
        with self.assertRaises(ValidationError):
            chain.build_transaction(
                key=alice.key,
                recipients=[(bob.address, 20)],
                policy=policy,
            )

    def test_first_transaction_starts_new_trajectory(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )

        self.assertIsNone(tx.prev)
        self.assertEqual(tx.sequence, 0)
        self.assertIsNotNone(tx.trajectory_id)
        self.assertEqual(tx.policy_hash, chain._policy_hash(policy))

    def test_next_transaction_extends_existing_trajectory(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx1 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx1, signer_seed=alice.seed)
        chain.mine_block(bob.address)

        tx2 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 5)],
            policy=policy,
            timestamp=102,
        )

        self.assertEqual(tx2.prev, tx1.txid)
        self.assertEqual(tx2.sequence, 1)
        self.assertEqual(tx2.trajectory_id, tx1.trajectory_id)

    def test_branch_conflict_is_rejected(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx1 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx1, signer_seed=alice.seed)

        conflicting = replace(
            tx1,
            txid=tx1.txid,
        )
        with self.assertRaises(ValidationError):
            chain.add_transaction(conflicting, signer_seed=alice.seed)

    def test_rate_limit_is_rejected(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            rate_limit_window=10,
            max_txs_per_window=1,
            min_tx_gap=0,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx1 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx1, signer_seed=alice.seed)
        chain.mine_block(bob.address)

        with self.assertRaises(ValidationError):
            chain.build_transaction(
                key=alice.key,
                recipients=[(bob.address, 5)],
                policy=policy,
                timestamp=105,
            )

    def test_new_producer_is_rejected_by_default(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        miner = Wallet("miner", "miner-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)

        with self.assertRaises(ValidationError):
            chain.mine_block(miner.address)

    def test_new_producer_can_mine_with_override(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        miner = Wallet("miner", "miner-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)
        block = chain.mine_block(miner.address)

        self.assertEqual(block.index, 1)


if __name__ == "__main__":
    unittest.main()
