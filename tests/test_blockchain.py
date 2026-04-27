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
        self.assertGreaterEqual(len(block.parents), 1)
        self.assertEqual(block.producer_id, miner.address)
        self.assertIn(block.producer_phase, {"new", "probation", "mature", "penalized"})

    def test_producer_priority_prefers_mature_over_new(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        mature = Wallet("mature", "mature-seed")
        new = Wallet("newbie", "newbie-seed")

        mature_state = chain._identity_state(mature.address)
        mature_state.phase = "mature"
        mature_state.compliant_txs = 25
        mature_state.average_delta = 0.2

        new_state = chain._identity_state(new.address)
        new_state.phase = "new"
        new_state.compliant_txs = 0
        new_state.average_delta = 0.0

        self.assertLess(
            chain.producer_priority(mature.address, proposed_timestamp=100),
            chain.producer_priority(new.address, proposed_timestamp=100),
        )

    def test_producer_priority_uses_delta_as_tiebreak(self) -> None:
        chain = Blockchain(difficulty=1, mining_reward=5)
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")

        a_state = chain._identity_state(a.address)
        a_state.phase = "mature"
        a_state.compliant_txs = 20
        a_state.average_delta = 0.1

        b_state = chain._identity_state(b.address)
        b_state.phase = "mature"
        b_state.compliant_txs = 20
        b_state.average_delta = 0.8

        self.assertLess(
            chain.producer_priority(a.address, proposed_timestamp=100),
            chain.producer_priority(b.address, proposed_timestamp=100),
        )

    def test_chain_summary_exposes_dag_parents(self) -> None:
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
        chain.mine_block(miner.address)

        summary = chain.chain_summary()
        self.assertIn("parents", summary[1])
        self.assertIsInstance(summary[1]["parents"], list)

    def test_virtual_order_supports_parallel_blocks(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")

        a_state = chain._identity_state(a.address)
        a_state.phase = "mature"
        a_state.compliant_txs = 30
        a_state.average_delta = 0.1

        b_state = chain._identity_state(b.address)
        b_state.phase = "mature"
        b_state.compliant_txs = 20
        b_state.average_delta = 0.3

        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        block_b = chain.build_candidate_block(b.address, transactions=[], parents=[parent])
        chain.accept_block(block_a)
        chain.accept_block(block_b)

        order = chain.virtual_order()
        self.assertEqual(order[0], parent)
        self.assertLess(order.index(block_a.block_hash), order.index(block_b.block_hash))

    def test_frontier_tracks_parallel_children(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")

        chain._identity_state(a.address).phase = "mature"
        chain._identity_state(b.address).phase = "mature"

        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        block_b = chain.build_candidate_block(b.address, transactions=[], parents=[parent])
        chain.accept_block(block_a)
        chain.accept_block(block_b)

        self.assertIn(block_a.block_hash, chain.frontier)
        self.assertIn(block_b.block_hash, chain.frontier)
        self.assertNotIn(parent, chain.frontier)

    def test_block_is_not_confirmed_without_successors(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
            confirmation_threshold=1.0,
        )
        a = Wallet("a", "a-seed")
        chain._identity_state(a.address).phase = "mature"
        parent = chain.blocks[-1].block_hash
        block = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        chain.accept_block(block)

        self.assertFalse(chain.is_confirmed(block.block_hash))
        self.assertEqual(chain.confirmation_score(block.block_hash), 0.0)

    def test_block_becomes_confirmed_with_weighted_successors(self) -> None:
        chain = Blockchain(
            difficulty=1,
            mining_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")

        a_state = chain._identity_state(a.address)
        a_state.phase = "mature"
        a_state.compliant_txs = 30
        a_state.average_delta = 0.1

        b_state = chain._identity_state(b.address)
        b_state.phase = "mature"
        b_state.compliant_txs = 30
        b_state.average_delta = 0.1

        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)

        self.assertGreater(chain.confirmation_score(block_a.block_hash), 0.5)
        self.assertTrue(chain.is_confirmed(block_a.block_hash))
        self.assertIn(block_a.block_hash, chain.confirmed_order())


if __name__ == "__main__":
    unittest.main()
