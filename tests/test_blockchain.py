"""Tests for the minimal blockchain prototype."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import subprocess
import sys
import tempfile
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
        chain = Blockchain(difficulty=1, producer_reward=5)
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
        chain = Blockchain(difficulty=1, producer_reward=5)
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
        chain = Blockchain(difficulty=1, producer_reward=5)
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
            producer_reward=5,
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
        chain.produce_block(bob.address)

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
        chain = Blockchain(difficulty=1, producer_reward=5)
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
            producer_reward=5,
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
        chain.produce_block(bob.address)

        with self.assertRaises(ValidationError):
            chain.build_transaction(
                key=alice.key,
                recipients=[(bob.address, 5)],
                policy=policy,
                timestamp=105,
            )

    def test_new_producer_is_rejected_by_default(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        producer = Wallet("producer", "producer-seed")
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
            chain.produce_block(producer.address)

    def test_new_producer_can_mine_with_override(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        producer = Wallet("producer", "producer-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)
        block = chain.produce_block(producer.address)

        self.assertEqual(block.index, 1)
        self.assertGreaterEqual(len(block.parents), 1)
        self.assertEqual(block.producer_id, producer.address)
        self.assertIn(block.producer_phase, {"new", "probation", "mature", "penalized"})

    def test_producer_priority_prefers_mature_over_new(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5)
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
        chain = Blockchain(difficulty=1, producer_reward=5)
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

    def test_identity_action_recovery_flow_updates_identity_store(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5)
        alice = Wallet("alice", "alice-seed")
        chain.register_identity(
            alice.address,
            [alice.address],
            guardian_keys=["g1", "g2", "g3"],
            recovery_threshold=2,
            recovery_delay_epochs=2,
        )

        start = chain.build_identity_action(
            key=alice.key,
            action_type="start_recovery",
            payload={
                "new_key": "alice-recovery-key",
                "approvals": [{"guardian": "g1"}, {"guardian": "g2"}],
            },
            timestamp=100,
        )
        chain.add_transaction(start, signer_seed=alice.seed)

        state = chain.identity_store.require(alice.address)
        self.assertEqual(start.identity_id, alice.address)
        self.assertEqual(start.action_key, alice.address)
        self.assertEqual(state.sequence, -1)

        producer = Wallet("producer", "producer-seed")
        chain._identity_state(producer.address).phase = "mature"
        chain._sync_identity_legitimacy(producer.address)
        chain.produce_block(producer.address)

        pending = chain.identity_store.require(alice.address).pending_recovery
        self.assertIsNotNone(pending)

        finalize = chain.build_identity_action(
            key=alice.key,
            action_type="finalize_recovery",
            payload={
                "new_key": "alice-recovery-key",
                "pending_recovery_id": pending["pending_recovery_id"],
            },
            timestamp=102,
        )
        chain.add_transaction(finalize, signer_seed=alice.seed)
        chain.produce_block(producer.address)

        finalized = chain.identity_store.require(alice.address)
        self.assertIsNone(finalized.pending_recovery)
        self.assertEqual(finalized.active_action_keys, ["alice-recovery-key"])

    def test_identity_store_ordering_score_feeds_producer_weight(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        producer = Wallet("producer", "producer-seed")
        state = chain._identity_state(producer.address)
        state.phase = "mature"
        state.compliant_txs = 50
        state.average_delta = 0.1
        chain.register_identity(producer.address, [producer.address])
        chain._sync_identity_legitimacy(producer.address)

        block = chain.produce_block(producer.address)
        store_state = chain.identity_store.require(producer.address)

        self.assertGreater(store_state.ordering_score, 0.0)
        self.assertEqual(block.producer_weight_snapshot, store_state.ordering_score)

    def test_chain_summary_exposes_dag_parents(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        producer = Wallet("producer", "producer-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)
        chain.produce_block(producer.address)

        summary = chain.chain_summary()
        self.assertIn("parents", summary[1])
        self.assertIsInstance(summary[1]["parents"], list)

    def test_virtual_order_supports_parallel_blocks(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
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

    def test_block_carries_weight_and_dynamic_k_snapshots(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        producer = Wallet("producer", "producer-seed")
        state = chain._identity_state(producer.address)
        state.phase = "mature"
        state.compliant_txs = 30
        state.average_delta = 0.1

        block = chain.build_candidate_block(producer.address, transactions=[], parents=[chain.blocks[-1].block_hash])

        self.assertAlmostEqual(block.producer_weight_snapshot, block.producer_ordering_score)
        self.assertGreaterEqual(block.dynamic_k_snapshot, 0.0)

    def test_weighted_anticone_view_tracks_parallel_conflicts(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")
        chain._identity_state(a.address).phase = "mature"
        chain._identity_state(a.address).compliant_txs = 30
        chain._identity_state(a.address).average_delta = 0.1
        chain._identity_state(b.address).phase = "mature"
        chain._identity_state(b.address).compliant_txs = 20
        chain._identity_state(b.address).average_delta = 0.3

        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        block_b = chain.build_candidate_block(b.address, transactions=[], parents=[parent])
        chain.accept_block(block_a)
        chain.accept_block(block_b)

        anticone_view = {item["block_hash"]: item for item in chain.weighted_anticone_view()}
        self.assertIn(block_b.block_hash, anticone_view[block_a.block_hash]["anticone"])
        self.assertIn(block_a.block_hash, anticone_view[block_b.block_hash]["anticone"])
        self.assertGreater(anticone_view[block_a.block_hash]["anticone_weight"], 0.0)

    def test_dynamic_k_is_positive_for_parallel_conflicts(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")
        chain._identity_state(a.address).phase = "mature"
        chain._identity_state(a.address).compliant_txs = 30
        chain._identity_state(b.address).phase = "mature"
        chain._identity_state(b.address).compliant_txs = 30

        parent = chain.blocks[-1].block_hash
        chain.accept_block(chain.build_candidate_block(a.address, transactions=[], parents=[parent]))
        chain.accept_block(chain.build_candidate_block(b.address, transactions=[], parents=[parent]))

        self.assertGreaterEqual(chain.dynamic_k(), 0.0)

    def test_frontier_tracks_parallel_children(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
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
            producer_reward=5,
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
            producer_reward=5,
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

    def test_unconfirmed_block_has_zero_reward(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=1.0,
        )
        a = Wallet("a", "a-seed")
        a_state = chain._identity_state(a.address)
        a_state.phase = "mature"
        a_state.compliant_txs = 30
        a_state.average_delta = 0.1

        parent = chain.blocks[-1].block_hash
        block = chain.build_candidate_block(a.address, transactions=[], parents=[parent])
        chain.accept_block(block)

        self.assertEqual(chain.confirmed_reward_for_block(block.block_hash), 0.0)

    def test_confirmed_reward_totals_credit_producer(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
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

        totals = chain.confirmed_reward_totals()
        self.assertIn(a.address, totals)
        self.assertGreater(totals[a.address], 0.0)

    def test_reward_amount_follows_emission_schedule(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=10,
            emission_schedule=[
                {"start_block": 1, "reward": 10},
                {"start_block": 3, "reward": 5},
                {"start_block": 5, "reward": 2},
            ],
            tail_reward_floor=1,
        )
        self.assertEqual(chain.reward_amount_for_block(1), 10)
        self.assertEqual(chain.reward_amount_for_block(3), 5)
        self.assertEqual(chain.reward_amount_for_block(5), 2)
        self.assertEqual(chain.reward_amount_for_block(8), 2)

    def test_confirmed_reward_uses_scheduled_reward_budget(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=10,
            emission_schedule=[
                {"start_block": 1, "reward": 10},
                {"start_block": 2, "reward": 4},
            ],
            tail_reward_floor=1,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        a = Wallet("a", "a-seed")
        b = Wallet("b", "b-seed")

        chain._identity_state(a.address).phase = "mature"
        chain._identity_state(a.address).compliant_txs = 30
        chain._identity_state(b.address).phase = "mature"
        chain._identity_state(b.address).compliant_txs = 30

        first = chain.build_candidate_block(a.address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(b.address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)

        reward = chain.confirmed_reward_for_block(first.block_hash)
        self.assertGreater(reward, 0.0)
        self.assertLessEqual(reward, 10.0)

    def test_confirmed_l1_batch_exports_confirmed_transactions(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        parent = chain.blocks[-1].block_hash

        chain._identity_state(prod_a.address).phase = "mature"
        chain._identity_state(prod_a.address).compliant_txs = 30
        chain._identity_state(prod_b.address).phase = "mature"
        chain._identity_state(prod_b.address).compliant_txs = 30

        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(prod_b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)

        batch = chain.confirmed_l1_batch()
        self.assertEqual(batch["mode"], "confirmed")
        self.assertIn(block_a.block_hash, batch["block_hashes"])
        self.assertTrue(any(item["txid"] == tx.txid for item in batch["transactions"]))
        tx_record = next(item for item in batch["transactions"] if item["txid"] == tx.txid)
        self.assertEqual(tx_record["sender"], alice.address)
        self.assertEqual(tx_record["producer_id"], prod_a.address)

    def test_export_l1_feed_virtual_marks_confirmation_status(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=1.0,
        )
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        chain._identity_state(prod_a.address).phase = "mature"
        chain._identity_state(prod_a.address).compliant_txs = 30
        chain._identity_state(prod_b.address).phase = "mature"
        chain._identity_state(prod_b.address).compliant_txs = 30

        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(prod_a.address, transactions=[], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(prod_b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)

        feed = chain.export_l1_feed(confirmed_only=False)
        self.assertEqual(feed["mode"], "virtual")
        self.assertEqual(feed["feed_scope"], "resolved_virtual")
        block_map = {item["block_hash"]: item for item in feed["blocks"]}
        self.assertTrue(block_map[block_a.block_hash]["confirmed"])
        self.assertFalse(block_map[block_b.block_hash]["confirmed"])

    def test_finality_summary_and_finalized_batch_follow_confirmed_prefix(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        prod_c = Wallet("prod-c", "prod-c-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        parent = chain.blocks[-1].block_hash

        for producer in (prod_a, prod_b, prod_c):
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(prod_b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)
        block_c = chain.build_candidate_block(prod_c.address, transactions=[], parents=[block_b.block_hash])
        chain.accept_block(block_c)

        checkpoints = chain.finality_checkpoints()
        summary = chain.finality_summary()
        batch = chain.finalized_l1_batch()

        self.assertGreaterEqual(len(checkpoints), 2)
        self.assertIsNotNone(summary["latest_locked_checkpoint"])
        self.assertIsNotNone(summary["latest_finalized_checkpoint"])
        self.assertGreaterEqual(summary["finalized_height"], 1)
        self.assertEqual(batch["mode"], "finalized")
        self.assertEqual(batch["feed_scope"], "finalized")
        self.assertEqual(batch["checkpoint_id"], summary["latest_finalized_checkpoint"])
        self.assertTrue(any(item["txid"] == tx.txid for item in batch["transactions"]))

    def test_export_l1_handoff_prefers_finalized_batch_when_available(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        producers = [Wallet(f"prod-{name}", f"prod-{name}-seed") for name in ("a", "b", "c")]
        for producer in producers:
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(producers[0].address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(producers[1].address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(producers[2].address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        handoff = chain.export_l1_handoff()

        self.assertEqual(handoff["finality_status"], "finalized")
        self.assertEqual(handoff["handoff_scope"], "finalized")
        self.assertEqual(handoff["checkpoint_id"], chain.finality_summary()["latest_finalized_checkpoint"])
        self.assertEqual(handoff["batch"]["mode"], "finalized")

    def test_export_l1_handoff_falls_back_to_confirmed_without_finalized_checkpoint(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        prod_a = Wallet("prod-a", "prod-a-seed")
        chain._identity_state(prod_a.address).phase = "mature"
        chain._identity_state(prod_a.address).compliant_txs = 30

        first = chain.build_candidate_block(prod_a.address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)

        handoff = chain.export_l1_handoff()

        self.assertEqual(handoff["finality_status"], "confirmed")
        self.assertEqual(handoff["handoff_scope"], "confirmed")
        self.assertIsNone(handoff["checkpoint_id"])
        self.assertEqual(handoff["batch"]["mode"], "confirmed")

    def test_finality_committee_uses_mature_identities_only(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        mature = Wallet("mature", "mature-seed")
        probation = Wallet("probation", "probation-seed")

        mature_state = chain._identity_state(mature.address)
        mature_state.phase = "mature"
        mature_state.compliant_txs = 40

        probation_state = chain._identity_state(probation.address)
        probation_state.phase = "probation"
        probation_state.compliant_txs = 40

        committee = chain.finality_committee()

        self.assertEqual([item.identity_id for item in committee], [mature.address])
        self.assertGreater(committee[0].finality_weight, 0.0)

    def test_verify_finality_checkpoint_rejects_tampered_prefix_digest(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        producers = [Wallet(f"prod-{name}", f"prod-{name}-seed") for name in ("a", "b", "c")]
        for producer in producers:
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(producers[0].address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(producers[1].address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(producers[2].address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        checkpoint = dict(chain.export_finality_state()["checkpoints"][1])
        checkpoint["ordered_prefix_digest"] = "0" * 64

        self.assertFalse(chain.verify_finality_checkpoint(checkpoint))

    def test_verify_finality_certificate_rejects_non_committee_signer(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        producers = [Wallet(f"prod-{name}", f"prod-{name}-seed") for name in ("a", "b", "c")]
        outsider = Wallet("outsider", "outsider-seed")
        for producer in producers:
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(producers[0].address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(producers[1].address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(producers[2].address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        checkpoint = chain.export_finality_state()["checkpoints"][1]
        certificate = dict(checkpoint["finalize_certificate"])
        certificate["signer_set"] = [outsider.address]

        self.assertFalse(chain.verify_finality_certificate(checkpoint["checkpoint_id"], certificate))

    def test_verify_finality_certificate_rejects_insufficient_quorum(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        producers = [Wallet(f"prod-{name}", f"prod-{name}-seed") for name in ("a", "b", "c")]
        for producer in producers:
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(producers[0].address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(producers[1].address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(producers[2].address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        checkpoint = chain.export_finality_state()["checkpoints"][1]
        certificate = dict(checkpoint["finalize_certificate"])
        certificate["quorum_weight"] = 0.5

        self.assertFalse(chain.verify_finality_certificate(checkpoint["checkpoint_id"], certificate))

    def test_virtual_order_rejects_parallel_double_spend(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx1 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        tx2 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=101,
        )
        parent = chain.blocks[-1].block_hash

        a_state = chain._identity_state(prod_a.address)
        a_state.phase = "mature"
        a_state.compliant_txs = 30
        a_state.average_delta = 0.1

        b_state = chain._identity_state(prod_b.address)
        b_state.phase = "mature"
        b_state.compliant_txs = 20
        b_state.average_delta = 0.2

        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx1], parents=[parent])
        block_b = chain.build_candidate_block(prod_b.address, transactions=[tx2], parents=[parent])
        chain.accept_block(block_a)
        chain.accept_block(block_b)

        resolved = chain.resolved_virtual_blocks()
        accepted = chain.accepted_virtual_transactions()
        self.assertIn(tx1.txid, accepted)
        self.assertNotIn(tx2.txid, accepted)
        self.assertTrue(any(tx2.txid in item["rejected_txids"] for item in resolved))

    def test_virtual_resolution_rejects_same_sender_sequence_conflict(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx1 = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        tx2 = replace(
            tx1,
            txid="conflict-seq",
            message=tx1.message + "|fork",
        )
        parent = chain.blocks[-1].block_hash

        chain._identity_state(prod_a.address).phase = "mature"
        chain._identity_state(prod_b.address).phase = "mature"

        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx1], parents=[parent])
        block_b = chain.build_candidate_block(prod_b.address, transactions=[tx2], parents=[parent])
        chain.accept_block(block_a)
        chain.accept_block(block_b)

        accepted = chain.accepted_virtual_transactions()
        kept = [txid for txid in (tx1.txid, tx2.txid) if txid in accepted]
        self.assertEqual(len(kept), 1)

    def test_blockchain_state_roundtrip_preserves_views(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        producer = Wallet("producer", "producer-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)
        chain.produce_block(producer.address)

        exported = chain.export_state()
        restored = Blockchain.from_state(exported)

        self.assertEqual(restored.chain_summary(), chain.chain_summary())
        self.assertEqual(restored.frontier, chain.frontier)
        self.assertEqual(restored.virtual_order(), chain.virtual_order())
        self.assertEqual(restored.confirmed_order(), chain.confirmed_order())
        self.assertEqual(restored.trajectory_summary(), chain.trajectory_summary())

    def test_export_state_json_is_stable_json(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        payload = chain.export_state_json()
        self.assertIsInstance(payload, str)
        self.assertIn("\"blocks\"", payload)
        self.assertIn(f"\"schema_version\":{Blockchain.SCHEMA_VERSION}", payload)
        self.assertIn("\"finality_state\"", payload)

    def test_finality_state_persists_across_roundtrip(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        prod_a = Wallet("prod-a", "prod-a-seed")
        prod_b = Wallet("prod-b", "prod-b-seed")
        prod_c = Wallet("prod-c", "prod-c-seed")
        for producer in (prod_a, prod_b, prod_c):
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(prod_a.address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(prod_b.address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(prod_c.address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        exported = chain.export_state()
        restored = Blockchain.from_state(exported)

        self.assertEqual(restored.export_finality_state(), chain.export_finality_state())
        self.assertEqual(restored.finality_summary(), chain.finality_summary())

    def test_from_state_recomputes_tampered_finality_cache(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
            confirmation_threshold=0.5,
        )
        producers = [Wallet(f"prod-{name}", f"prod-{name}-seed") for name in ("a", "b", "c")]
        for producer in producers:
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        first = chain.build_candidate_block(producers[0].address, transactions=[], parents=[chain.blocks[-1].block_hash])
        chain.accept_block(first)
        second = chain.build_candidate_block(producers[1].address, transactions=[], parents=[first.block_hash])
        chain.accept_block(second)
        third = chain.build_candidate_block(producers[2].address, transactions=[], parents=[second.block_hash])
        chain.accept_block(third)

        exported = chain.export_state()
        exported["finality_state"]["summary"]["latest_finalized_checkpoint"] = "tampered-checkpoint"
        exported["finality_state"]["summary"]["finalized_prefix_digest"] = "bad-digest"

        restored = Blockchain.from_state(exported)

        self.assertEqual(restored.finality_summary(), chain.finality_summary())
        self.assertEqual(restored.export_finality_state(), chain.export_finality_state())

    def test_save_and_load_state_file_roundtrip(self) -> None:
        chain = Blockchain(
            difficulty=1,
            producer_reward=5,
            allow_new_producers=True,
        )
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        producer = Wallet("producer", "producer-seed")
        chain.faucet(alice.address, 50)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=25)

        tx = chain.build_transaction(
            key=alice.key,
            recipients=[(bob.address, 10)],
            policy=policy,
            timestamp=100,
        )
        chain.add_transaction(tx, signer_seed=alice.seed)
        chain.produce_block(producer.address)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = chain.save_state(Path(tmpdir) / "chain_state.json")
            restored = Blockchain.load_state(path)

        self.assertEqual(restored.chain_summary(), chain.chain_summary())
        self.assertEqual(restored.virtual_order(), chain.virtual_order())
        self.assertEqual(restored.frontier, chain.frontier)

    def test_default_state_path_uses_poct_dir(self) -> None:
        path = Blockchain.default_state_path()
        self.assertEqual(path, Path(".poct") / "chain_state.json")

    def test_from_state_rejects_wrong_schema_version(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        state = chain.export_state()
        state["schema_version"] = 999
        with self.assertRaises(ValidationError):
            Blockchain.from_state(state)

    def test_save_state_writes_final_file_atomically(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "chain.json"
            chain.save_state(path)
            self.assertTrue(path.exists())
            self.assertFalse((Path(tmpdir) / "chain.json.tmp").exists())

    def test_cli_save_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            save = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "save",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("saved_to", save.stdout)
            load = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "load",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"summary\"", load.stdout)

    def test_cli_persist_demo_and_show_virtual(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            persist = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "persist-demo",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("virtual_order", persist.stdout)
            show_virtual = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-virtual",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"virtual_order\"", show_virtual.stdout)

    def test_cli_show_dag_and_resolved(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "persist-demo",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            show_dag = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-dag",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"dag\"", show_dag.stdout)
            show_resolved = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-resolved",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"resolved_virtual_blocks\"", show_resolved.stdout)

    def test_cli_show_l1_feed(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "persist-demo",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            show_l1 = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-l1-feed",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"transactions\"", show_l1.stdout)
            self.assertIn("\"mode\": \"confirmed\"", show_l1.stdout)

    def test_cli_show_l1_handoff(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "persist-demo",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            show_handoff = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-l1-handoff",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"batch\"", show_handoff.stdout)
            self.assertIn("\"finality_status\": \"confirmed\"", show_handoff.stdout)


if __name__ == "__main__":
    unittest.main()
