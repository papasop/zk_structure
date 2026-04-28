from __future__ import annotations

import multiprocessing
import tempfile
import unittest
from pathlib import Path

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.app.wallet_web import render_wallet_page
from structural_crypto.l1 import SimpleL1Executor
from structural_crypto.ledger import Blockchain
from structural_crypto.node import Wallet
from structural_crypto.node.node import PoCTNode
from structural_crypto.node.p2p import GossipEnvelope, PeerInfo
from structural_crypto.node.rpc import RPCRequest, RPCResponse
from structural_crypto.testing.loadgen import AgentSpec, LoadGenerator
from structural_crypto.zk import MockZKBackend


def _produce_block_to_spool(spool_dir: str) -> None:
    node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
    producer = Wallet("producer-a", "producer-a-seed")
    node.chain._identity_state(producer.address).phase = "mature"
    node.chain._identity_state(producer.address).compliant_txs = 30
    node.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
    node.produce_block(producer.address)
    node.write_envelopes(spool_dir)


class NodeL1ZKTests(unittest.TestCase):
    @staticmethod
    def _seed_mature_finality_nodes(*nodes: PoCTNode, producers: tuple[Wallet, ...]) -> None:
        for node in nodes:
            for producer in producers:
                node.chain._identity_state(producer.address).phase = "mature"
                node.chain._identity_state(producer.address).compliant_txs = 30

    def test_node_sync_summary_and_rpc(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        peer = PeerInfo(node_id="node-b", endpoint="127.0.0.1:9001")
        node.add_peer(peer)

        summary = node.sync_summary()
        self.assertEqual(summary["node_id"], "node-a")
        self.assertIn("finality", summary)
        self.assertEqual(summary["finality"]["current_finality_round"], 1)
        response = node.handle_rpc(RPCRequest(method="get_frontier"))
        self.assertTrue(response.ok)
        self.assertIn("frontier", response.result)

    def test_node_finality_summary_and_rpc_surface(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )

        for producer in (producer_a, producer_b, producer_c):
            node.chain._identity_state(producer.address).phase = "mature"
            node.chain._identity_state(producer.address).compliant_txs = 30
        node.finality_voter_id = producer_a.address

        block_a = node.produce_block(producer_a.address)
        node.chain.accept_block(
            node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[block_a.block_hash])
        )
        node.chain.accept_block(
            node.chain.build_candidate_block(
                producer_c.address,
                transactions=[],
                parents=[node.chain.blocks[-1].block_hash],
            )
        )

        summary = node.finality_summary()
        self.assertIsNotNone(summary["latest_finalized_checkpoint"])

        finality_response = node.handle_rpc(RPCRequest(method="get_finality_summary"))
        self.assertTrue(finality_response.ok)
        self.assertEqual(finality_response.result["latest_finalized_checkpoint"], summary["latest_finalized_checkpoint"])

        committee_response = node.handle_rpc(RPCRequest(method="get_committee"))
        self.assertTrue(committee_response.ok)
        self.assertGreaterEqual(len(committee_response.result["committee"]), 1)

        checkpoint_response = node.handle_rpc(
            RPCRequest(method="get_checkpoint", params={"checkpoint_id": summary["latest_finalized_checkpoint"]})
        )
        self.assertTrue(checkpoint_response.ok)

        certificate_response = node.handle_rpc(
            RPCRequest(method="get_certificate", params={"checkpoint_id": summary["latest_finalized_checkpoint"]})
        )
        self.assertTrue(certificate_response.ok)

        batch_response = node.handle_rpc(RPCRequest(method="get_finalized_batch"))
        self.assertTrue(batch_response.ok)
        self.assertEqual(batch_response.result["mode"], "finalized")

        handoff_response = node.handle_rpc(RPCRequest(method="get_l1_handoff"))
        self.assertTrue(handoff_response.ok)
        self.assertEqual(handoff_response.result["finality_status"], "finalized")
        self.assertEqual(handoff_response.result["batch"]["mode"], "finalized")

        vote_response = node.handle_rpc(RPCRequest(method="cast_finality_vote"))
        self.assertTrue(vote_response.ok)
        self.assertEqual(vote_response.result["vote"]["vote_type"], "lock")

        advance_response = node.handle_rpc(RPCRequest(method="advance_finality_round"))
        self.assertTrue(advance_response.ok)
        self.assertGreaterEqual(advance_response.result["current_finality_round"], 1)

        timeout_response = node.handle_rpc(RPCRequest(method="finality_timeout_tick"))
        self.assertTrue(timeout_response.ok)
        self.assertIn("reason", timeout_response.result)

        dagknight_response = node.handle_rpc(RPCRequest(method="get_dagknight_summary"))
        self.assertTrue(dagknight_response.ok)
        self.assertIn("dynamic_k", dagknight_response.result)
        self.assertIn("blue_set", dagknight_response.result)

    def test_node_can_reconcile_and_persist_finality_evidence(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        for producer in (producer_a, producer_b, producer_c):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        node_b.reconcile_with_peer(node_a.handle_rpc)
        result = node_b.reconcile_finality_with_peer(node_a.handle_rpc)

        self.assertTrue(result["verified"])
        self.assertIn(result["checkpoint_id"], node_b.verified_finality_evidence)

        with tempfile.TemporaryDirectory() as tmpdir:
            path = node_b.save(Path(tmpdir) / "node.json")
            restored = PoCTNode.load("node-b", path)
        self.assertIn(result["checkpoint_id"], restored.verified_finality_evidence)

    def test_finality_votes_form_certificate_and_adopt_checkpoint(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_b.address,
        )
        node_c = PoCTNode(
            "node-c",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_c.address,
        )
        self._seed_mature_finality_nodes(node_a, node_b, node_c, producers=(producer_a, producer_b, producer_c))

        for left, right in ((node_a, node_b), (node_a, node_c), (node_b, node_a), (node_b, node_c), (node_c, node_a), (node_c, node_b)):
            left.add_peer(PeerInfo(node_id=right.node_id, endpoint="local-spool"))

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        node_b.fetch_missing_block_via_rpc(node_a.handle_rpc, third.block_hash)
        node_c.fetch_missing_block_via_rpc(node_a.handle_rpc, third.block_hash)

        latest_checkpoint = node_a.chain.export_finality_state()["checkpoints"][-1]
        previous_checkpoint = node_a.chain.export_finality_state()["checkpoints"][-2]

        self.assertIsNotNone(node_a.cast_finality_vote(latest_checkpoint["checkpoint_id"]))
        self.assertIsNotNone(node_b.cast_finality_vote(latest_checkpoint["checkpoint_id"]))
        self.assertIsNotNone(node_c.cast_finality_vote(latest_checkpoint["checkpoint_id"]))

        with tempfile.TemporaryDirectory() as tmpdir:
            node_a.write_envelopes(tmpdir)
            node_b.write_envelopes(tmpdir)
            node_c.write_envelopes(tmpdir)
            node_a.read_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_c.read_envelopes(tmpdir)
            node_a.process_inbox()
            node_b.process_inbox()
            node_c.process_inbox()

            node_a.write_envelopes(tmpdir)
            node_b.write_envelopes(tmpdir)
            node_c.write_envelopes(tmpdir)
            node_a.read_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_c.read_envelopes(tmpdir)
            node_a.process_inbox()
            node_b.process_inbox()
            node_c.process_inbox()

        for node in (node_a, node_b, node_c):
            self.assertIn(latest_checkpoint["checkpoint_id"], node.finality_certificates)
            self.assertEqual(node.adopted_finality_checkpoint_id, previous_checkpoint["checkpoint_id"])
            self.assertIn(previous_checkpoint["checkpoint_id"], node.verified_finality_evidence)

    def test_conflicting_vote_from_same_voter_is_rejected_and_recorded(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        checkpoints = node.chain.export_finality_state()["checkpoints"]
        checkpoint_round_2 = checkpoints[1]
        existing_vote = {
            "epoch": checkpoint_round_2["epoch"],
            "round": checkpoint_round_2["round"],
            "vote_type": "lock",
            "checkpoint_id": checkpoint_round_2["checkpoint_id"],
            "committee_digest": checkpoint_round_2["committee_digest"],
            "voter_id": producer_a.address,
            "voter_weight": node.chain.finality_weight_map()[producer_a.address],
            "vote_digest": node.chain._finality_vote_digest(
                epoch=checkpoint_round_2["epoch"],
                round_index=checkpoint_round_2["round"],
                vote_type="lock",
                checkpoint_id=checkpoint_round_2["checkpoint_id"],
                committee_digest=checkpoint_round_2["committee_digest"],
                voter_id=producer_a.address,
                voter_weight=node.chain.finality_weight_map()[producer_a.address],
            ),
        }
        self.assertTrue(node._record_finality_vote(checkpoint_round_2, existing_vote))

        conflicting_checkpoint = dict(checkpoint_round_2)
        conflicting_checkpoint["checkpoint_id"] = "conflicting-checkpoint"
        conflicting_checkpoint["ordered_prefix_digest"] = checkpoint_round_2["ordered_prefix_digest"]
        conflicting_checkpoint["confirmed_batch_digest"] = checkpoint_round_2["confirmed_batch_digest"]
        conflicting_checkpoint["anchor_block_hash"] = checkpoint_round_2["anchor_block_hash"]
        conflicting_vote = {
            **existing_vote,
            "checkpoint_id": "conflicting-checkpoint",
            "vote_digest": node.chain._finality_vote_digest(
                epoch=checkpoint_round_2["epoch"],
                round_index=checkpoint_round_2["round"],
                vote_type="lock",
                checkpoint_id="conflicting-checkpoint",
                committee_digest=checkpoint_round_2["committee_digest"],
                voter_id=producer_a.address,
                voter_weight=node.chain.finality_weight_map()[producer_a.address],
            ),
        }

        accepted = node._record_finality_vote(conflicting_checkpoint, conflicting_vote)

        self.assertFalse(accepted)
        self.assertTrue(any(item["type"] == "conflicting-vote" for item in node.finality_conflicts))

    def test_conflicting_certificate_is_rejected_and_recorded(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        checkpoint = node.chain.export_finality_state()["checkpoints"][1]
        signer_set = sorted(node.chain.finality_weight_map().keys())
        existing_certificate = node.chain._certificate_to_dict(
            node.chain._build_finality_certificate(
                epoch=checkpoint["epoch"],
                round_index=checkpoint["round"],
                vote_type="lock",
                checkpoint_id=checkpoint["checkpoint_id"],
                committee_digest=checkpoint["committee_digest"],
                quorum_weight=sum(node.chain.finality_weight_map().values()),
                signers=signer_set,
            )
        )
        self.assertTrue(node.verify_and_store_live_finality_certificate(checkpoint, existing_certificate))

        conflicting_checkpoint = dict(checkpoint)
        conflicting_checkpoint["checkpoint_id"] = "conflicting-checkpoint"
        conflicting_certificate = node.chain._certificate_to_dict(
            node.chain._build_finality_certificate(
                epoch=checkpoint["epoch"],
                round_index=checkpoint["round"],
                vote_type="lock",
                checkpoint_id="conflicting-checkpoint",
                committee_digest=checkpoint["committee_digest"],
                quorum_weight=sum(node.chain.finality_weight_map().values()),
                signers=signer_set,
            )
        )

        accepted = node.verify_and_store_live_finality_certificate(conflicting_checkpoint, conflicting_certificate)

        self.assertFalse(accepted)
        self.assertTrue(any(item["type"] == "conflicting-certificate" for item in node.finality_conflicts))

    def test_node_save_and_load_preserves_live_finality_vote_state(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)
        latest_checkpoint = node.chain.export_finality_state()["checkpoints"][-1]
        previous_checkpoint = node.chain.export_finality_state()["checkpoints"][-2]

        node.finality_votes[latest_checkpoint["checkpoint_id"]] = {
            producer_a.address: {
                "epoch": latest_checkpoint["epoch"],
                "round": latest_checkpoint["round"],
                "vote_type": "lock",
                "checkpoint_id": latest_checkpoint["checkpoint_id"],
                "committee_digest": latest_checkpoint["committee_digest"],
                "voter_id": producer_a.address,
                "voter_weight": node.chain.finality_weight_map()[producer_a.address],
                "vote_digest": "vote-digest",
            }
        }
        node.finality_certificates[previous_checkpoint["checkpoint_id"]] = {
            "checkpoint": previous_checkpoint,
            "certificate": {"checkpoint_id": previous_checkpoint["checkpoint_id"], "vote_type": "finalize"},
        }
        node.finality_conflicts.append({"type": "conflicting-vote", "round": latest_checkpoint["round"]})
        node.adopted_finality_checkpoint_id = previous_checkpoint["checkpoint_id"]
        node.current_finality_round = latest_checkpoint["round"]
        node.current_finality_checkpoint_id = latest_checkpoint["checkpoint_id"]
        node.finality_timeout_ticks = 2
        node.finality_timeout_limit = 5

        with tempfile.TemporaryDirectory() as tmpdir:
            path = node.save(Path(tmpdir) / "node.json")
            restored = PoCTNode.load("node-a", path)

        self.assertEqual(restored.finality_voter_id, producer_a.address)
        self.assertIn(latest_checkpoint["checkpoint_id"], restored.finality_votes)
        self.assertIn(previous_checkpoint["checkpoint_id"], restored.finality_certificates)
        self.assertEqual(restored.finality_conflicts, node.finality_conflicts)
        self.assertEqual(restored.adopted_finality_checkpoint_id, previous_checkpoint["checkpoint_id"])
        self.assertEqual(restored.current_finality_round, latest_checkpoint["round"])
        self.assertEqual(restored.current_finality_checkpoint_id, latest_checkpoint["checkpoint_id"])
        self.assertEqual(restored.finality_timeout_ticks, 2)
        self.assertEqual(restored.finality_timeout_limit, 5)

    def test_advance_finality_round_initializes_current_checkpoint(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        checkpoint = node.advance_finality_round()

        self.assertIsNotNone(checkpoint)
        self.assertEqual(node.current_finality_round, 1)
        self.assertEqual(node.current_finality_checkpoint_id, checkpoint["checkpoint_id"])

    def test_advance_finality_round_moves_forward_after_quorum_certificate(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        latest_checkpoint = node.chain.export_finality_state()["checkpoints"][-1]
        previous_checkpoint = node.chain.export_finality_state()["checkpoints"][-2]

        node.advance_finality_round(force=True)
        node.current_finality_round = previous_checkpoint["round"]
        node.current_finality_checkpoint_id = previous_checkpoint["checkpoint_id"]
        node.finality_certificates[previous_checkpoint["checkpoint_id"]] = {
            "checkpoint": previous_checkpoint,
            "certificate": {"checkpoint_id": previous_checkpoint["checkpoint_id"], "vote_type": "lock"},
        }

        advanced = node.advance_finality_round()

        self.assertEqual(advanced["checkpoint_id"], latest_checkpoint["checkpoint_id"])
        self.assertEqual(node.current_finality_round, latest_checkpoint["round"])

    def test_timeout_tick_retries_vote_after_limit(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        latest_checkpoint = node.chain.export_finality_state()["checkpoints"][-1]
        node.current_finality_round = latest_checkpoint["round"]
        node.current_finality_checkpoint_id = latest_checkpoint["checkpoint_id"]
        node.finality_timeout_limit = 2

        first_tick = node.timeout_tick()
        second_tick = node.timeout_tick()

        self.assertEqual(first_tick["reason"], "waiting")
        self.assertEqual(second_tick["reason"], "retry-vote")
        self.assertEqual(second_tick["checkpoint_id"], latest_checkpoint["checkpoint_id"])

    def test_timeout_tick_advances_when_vote_already_exists_but_retry_is_unavailable(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
            finality_voter_id=producer_a.address,
        )
        self._seed_mature_finality_nodes(node, producers=(producer_a, producer_b, producer_c))

        first = node.produce_block(producer_a.address)
        second = node.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node.chain.accept_block(second)
        third = node.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node.chain.accept_block(third)

        latest_checkpoint = node.chain.export_finality_state()["checkpoints"][-1]
        node.current_finality_round = 1
        node.current_finality_checkpoint_id = node.chain.export_finality_state()["checkpoints"][0]["checkpoint_id"]
        node.finality_timeout_limit = 1
        existing_vote = node.cast_finality_vote(node.current_finality_checkpoint_id)
        self.assertIsNotNone(existing_vote)

        result = node.timeout_tick()

        self.assertEqual(result["reason"], "advance-round")
        self.assertGreaterEqual(node.current_finality_round, 2)

    def test_finality_gossip_requests_and_verifies_evidence(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node_b.add_peer(PeerInfo(node_id="node-a", endpoint="local-spool"))

        for producer in (producer_a, producer_b, producer_c):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        node_b.reconcile_with_peer(node_a.handle_rpc)
        node_a.announce_finality_summary()

        with tempfile.TemporaryDirectory() as tmpdir:
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()
            node_b.write_envelopes(tmpdir)
            node_a.read_envelopes(tmpdir)
            node_a.process_inbox()
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()

        checkpoint_id = node_a.finality_summary()["latest_finalized_checkpoint"]
        self.assertIn(checkpoint_id, node_b.verified_finality_evidence)

    def test_verify_and_store_finality_evidence_rejects_tampered_checkpoint(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )

        for producer in (producer_a, producer_b, producer_c):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        node_b.fetch_missing_block_via_rpc(node_a.handle_rpc, third.block_hash)
        checkpoint_id = node_a.finality_summary()["latest_finalized_checkpoint"]
        checkpoint = next(
            item
            for item in node_a.chain.export_finality_state()["checkpoints"]
            if item["checkpoint_id"] == checkpoint_id
        )
        certificate = node_a.handle_rpc(
            RPCRequest(method="get_certificate", params={"checkpoint_id": checkpoint_id})
        ).result["certificate"]
        tampered_checkpoint = dict(checkpoint)
        tampered_checkpoint["anchor_block_hash"] = "f" * 64

        verified = node_b.verify_and_store_finality_evidence(tampered_checkpoint, certificate)

        self.assertFalse(verified)
        self.assertNotIn(checkpoint_id, node_b.verified_finality_evidence)

    def test_node_submit_transaction_emits_gossip(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        node = PoCTNode("node-a", chain=chain)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 10)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=5, allowed_recipients=[bob.address])
        tx = chain.build_transaction(alice.key, [(bob.address, 5)], policy, timestamp=100)

        node.submit_transaction(tx, signer_seed=alice.seed)

        self.assertEqual(node.outbox[-1].kind, "transaction")
        self.assertEqual(node.outbox[-1].payload["txid"], tx.txid)

    def test_transaction_gossip_imports_into_peer_mempool(self) -> None:
        chain_a = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        chain_b = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        node_a = PoCTNode("node-a", chain=chain_a)
        node_b = PoCTNode("node-b", chain=chain_b)
        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain_a.faucet(alice.address, 10)
        chain_b.faucet(alice.address, 10)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=5, allowed_recipients=[bob.address])
        tx = chain_a.build_transaction(alice.key, [(bob.address, 5)], policy, timestamp=100)

        node_a.submit_transaction(tx, signer_seed=alice.seed)
        with tempfile.TemporaryDirectory() as tmpdir:
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()

        self.assertTrue(any(item.txid == tx.txid for item in node_b.chain.mempool))

    def test_node_can_sync_missing_frontier_blocks_from_peer(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_a.chain._identity_state(producer.address).phase = "mature"
        node_a.chain._identity_state(producer.address).compliant_txs = 30

        block = node_a.produce_block(producer.address)
        imported = node_b.sync_blocks_from_peer(node_a)

        self.assertIn(block.block_hash, imported)
        self.assertIn(block.block_hash, node_b.chain.block_by_hash)
        self.assertEqual(node_b.chain.frontier, node_a.chain.frontier)

    def test_fetch_missing_block_via_rpc_imports_parent_chain(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_a.chain._identity_state(producer.address).phase = "mature"
        node_a.chain._identity_state(producer.address).compliant_txs = 30

        block_1 = node_a.produce_block(producer.address)
        block_2 = node_a.produce_block(producer.address)
        fetched = node_b.fetch_missing_block_via_rpc(node_a.handle_rpc, block_2.block_hash)

        self.assertEqual(fetched, block_2.block_hash)
        self.assertIn(block_1.block_hash, node_b.chain.block_by_hash)
        self.assertIn(block_2.block_hash, node_b.chain.block_by_hash)

    def test_reconcile_with_peer_uses_sync_summary_and_rpc(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_a.chain._identity_state(producer.address).phase = "mature"
        node_a.chain._identity_state(producer.address).compliant_txs = 30

        block = node_a.produce_block(producer.address)
        imported = node_b.reconcile_with_peer(node_a.handle_rpc)

        self.assertIn(block.block_hash, imported)
        self.assertEqual(node_b.chain.frontier, node_a.chain.frontier)

    def test_reconcile_with_peer_prioritizes_finality_evidence(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        for producer in (producer_a, producer_b, producer_c):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        imported = node_b.reconcile_with_peer(node_a.handle_rpc)
        checkpoint_id = node_a.finality_summary()["latest_finalized_checkpoint"]

        self.assertTrue(imported)
        self.assertIn(checkpoint_id, node_b.verified_finality_evidence)

    def test_reconcile_finality_with_peer_reports_unavailable_summary(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))

        def unavailable_summary(request: RPCRequest) -> RPCResponse:
            if request.method == "get_finality_summary":
                return RPCResponse(ok=False, error="offline")
            return RPCResponse(ok=False, error="unexpected")

        result = node.reconcile_finality_with_peer(unavailable_summary)

        self.assertFalse(result["verified"])
        self.assertEqual(result["reason"], "summary-unavailable")

    def test_file_spool_gossip_transfers_block(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_a.chain._identity_state(producer.address).phase = "mature"
        node_a.chain._identity_state(producer.address).compliant_txs = 30
        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))

        block = node_a.produce_block(producer.address)
        with tempfile.TemporaryDirectory() as tmpdir:
            written = node_a.write_envelopes(tmpdir)
            self.assertGreater(written, 0)
            read = node_b.read_envelopes(tmpdir)
            self.assertGreater(read, 0)
            processed = node_b.process_inbox()

        self.assertGreater(processed, 0)
        self.assertIn(block.block_hash, node_b.chain.block_by_hash)
        self.assertEqual(node_b.chain.frontier, node_a.chain.frontier)

    def test_multiprocess_local_gossip_syncs_block(self) -> None:
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        with tempfile.TemporaryDirectory() as tmpdir:
            proc = multiprocessing.Process(target=_produce_block_to_spool, args=(tmpdir,))
            proc.start()
            proc.join(timeout=10)
            self.assertEqual(proc.exitcode, 0)

            read = node_b.read_envelopes(tmpdir)
            processed = node_b.process_inbox()

        self.assertGreater(read, 0)
        self.assertGreater(processed, 0)
        self.assertGreater(len(node_b.chain.blocks), 1)

    def test_node_save_and_load(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        with tempfile.TemporaryDirectory() as tmpdir:
            path = node.save(Path(tmpdir) / "node.json")
            restored = PoCTNode.load("node-a", path)
        self.assertEqual(restored.chain.chain_summary(), node.chain.chain_summary())

    def test_node_save_and_load_preserves_network_state(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node.receive(GossipEnvelope(kind="sync-summary", origin="node-b", payload={"frontier": []}, ttl=4))
        node.spool_sequence = 7
        with tempfile.TemporaryDirectory() as tmpdir:
            path = node.save(Path(tmpdir) / "node.json")
            restored = PoCTNode.load("node-a", path)
        self.assertIn("node-b", restored.peers)
        self.assertEqual(restored.peers["node-b"].endpoint, "local-spool")
        self.assertEqual(len(restored.inbox), 1)
        self.assertEqual(restored.spool_sequence, 7)
        self.assertEqual(restored.seen_envelopes, node.seen_envelopes)

    def test_duplicate_gossip_envelope_is_processed_once(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        envelope = GossipEnvelope(kind="sync-summary", origin="node-b", payload={"frontier": []}, ttl=4)

        node.receive(envelope)
        node.receive(envelope)

        self.assertEqual(len(node.inbox), 1)
        processed = node.process_inbox()
        self.assertEqual(processed, 1)

    def test_write_envelopes_does_not_overwrite_prior_batch(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node.outbox.append(GossipEnvelope(kind="sync-summary", origin="node-a", payload={"frontier": []}))
        with tempfile.TemporaryDirectory() as tmpdir:
            first_written = node.write_envelopes(tmpdir)
            node.outbox.append(GossipEnvelope(kind="sync-summary", origin="node-a", payload={"frontier": ["x"]}))
            second_written = node.write_envelopes(tmpdir)
            files = sorted((Path(tmpdir) / "node-b").glob("*.json"))
        self.assertEqual(first_written, 1)
        self.assertEqual(second_written, 1)
        self.assertEqual(len(files), 2)

    def test_write_envelopes_respects_target_peer_metadata(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node.add_peer(PeerInfo(node_id="node-c", endpoint="local-spool"))
        node.outbox.append(
            GossipEnvelope(
                kind="sync-request",
                origin="node-a",
                payload={"block_hashes": ["abc"]},
                metadata={"target_peer_id": "node-b"},
            )
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            written = node.write_envelopes(tmpdir)
            node_b_files = sorted((Path(tmpdir) / "node-b").glob("*.json"))
            node_c_dir = Path(tmpdir) / "node-c"

        self.assertEqual(written, 1)
        self.assertEqual(len(node_b_files), 1)
        self.assertFalse(node_c_dir.exists())

    def test_reconciled_nodes_report_convergence(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))

        first = node_a.produce_block(producer.address)
        second = node_a.produce_block(producer.address)
        imported = node_b.reconcile_with_peer(node_a.handle_rpc)
        comparison = node_b.compare_sync_summary(node_a.sync_summary())

        self.assertIn(first.block_hash, node_b.chain.block_by_hash)
        self.assertIn(second.block_hash, node_b.chain.block_by_hash)
        self.assertGreaterEqual(len(imported), 1)
        self.assertTrue(comparison["config_match"])
        self.assertTrue(comparison["consensus_match"])
        self.assertTrue(comparison["frontier_match"])
        self.assertTrue(comparison["virtual_order_match"])
        self.assertTrue(comparison["confirmed_order_match"])
        self.assertTrue(node_b.has_converged_with_peer(node_a.sync_summary()))

    def test_sync_summary_request_flow_fetches_missing_blocks(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node_b.add_peer(PeerInfo(node_id="node-a", endpoint="local-spool"))

        block = node_a.produce_block(producer.address)
        node_a.announce_sync_summary()

        with tempfile.TemporaryDirectory() as tmpdir:
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()
            node_b.write_envelopes(tmpdir)
            node_a.read_envelopes(tmpdir)
            node_a.process_inbox()
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()

        self.assertIn(block.block_hash, node_b.chain.block_by_hash)
        self.assertTrue(node_b.has_converged_with_peer(node_a.sync_summary()))

    def test_sync_summary_requests_finality_evidence_before_frontier_blocks(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node_b.add_peer(PeerInfo(node_id="node-a", endpoint="local-spool"))
        for producer in (producer_a, producer_b, producer_c):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        node_b.receive(GossipEnvelope(kind="sync-summary", origin="node-a", payload=node_a.sync_summary(), ttl=4))
        node_b.process_inbox()

        self.assertEqual(node_b.outbox[-1].kind, "finality-request")

    def test_sync_summary_with_verified_checkpoint_requests_missing_frontier_blocks(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        producer_d = Wallet("producer-d", "producer-d-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )

        for producer in (producer_a, producer_b, producer_c, producer_d):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        checkpoint_id = node_a.finality_summary()["latest_finalized_checkpoint"]
        checkpoint = next(
            item
            for item in node_a.chain.export_finality_state()["checkpoints"]
            if item["checkpoint_id"] == checkpoint_id
        )
        certificate = node_a.handle_rpc(
            RPCRequest(method="get_certificate", params={"checkpoint_id": checkpoint_id})
        ).result["certificate"]

        node_b.fetch_missing_block_via_rpc(node_a.handle_rpc, third.block_hash)
        self.assertTrue(node_b.verify_and_store_finality_evidence(checkpoint, certificate))

        fourth = node_a.chain.build_candidate_block(producer_d.address, transactions=[], parents=[third.block_hash])
        node_a.chain.accept_block(fourth)

        node_b.receive(
            GossipEnvelope(
                kind="sync-summary",
                origin="node-a",
                payload={
                    "frontier": [fourth.block_hash],
                    "finality": {"latest_finalized_checkpoint": checkpoint_id},
                },
                ttl=4,
            )
        )
        node_b.process_inbox()

        self.assertEqual(node_b.outbox[-1].kind, "sync-request")
        self.assertEqual(node_b.outbox[-1].payload["block_hashes"], [fourth.block_hash])

    def test_finality_evidence_requests_frontier_when_finalized_blocks_are_already_local(self) -> None:
        producer_a = Wallet("producer-a", "producer-a-seed")
        producer_b = Wallet("producer-b", "producer-b-seed")
        producer_c = Wallet("producer-c", "producer-c-seed")
        producer_d = Wallet("producer-d", "producer-d-seed")
        node_a = PoCTNode(
            "node-a",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )
        node_b = PoCTNode(
            "node-b",
            chain=Blockchain(difficulty=1, allow_new_producers=True, confirmation_threshold=0.5),
        )

        for producer in (producer_a, producer_b, producer_c, producer_d):
            node_a.chain._identity_state(producer.address).phase = "mature"
            node_a.chain._identity_state(producer.address).compliant_txs = 30
            node_b.chain._identity_state(producer.address).phase = "mature"
            node_b.chain._identity_state(producer.address).compliant_txs = 30

        first = node_a.produce_block(producer_a.address)
        second = node_a.chain.build_candidate_block(producer_b.address, transactions=[], parents=[first.block_hash])
        node_a.chain.accept_block(second)
        third = node_a.chain.build_candidate_block(producer_c.address, transactions=[], parents=[second.block_hash])
        node_a.chain.accept_block(third)

        checkpoint_id = node_a.finality_summary()["latest_finalized_checkpoint"]
        checkpoint = next(
            item
            for item in node_a.chain.export_finality_state()["checkpoints"]
            if item["checkpoint_id"] == checkpoint_id
        )
        certificate = node_a.handle_rpc(
            RPCRequest(method="get_certificate", params={"checkpoint_id": checkpoint_id})
        ).result["certificate"]

        finalized_hashes = list(node_a.chain.finalized_l1_batch()["block_hashes"])
        node_b.fetch_missing_block_via_rpc(node_a.handle_rpc, third.block_hash)

        fourth = node_a.chain.build_candidate_block(producer_d.address, transactions=[], parents=[third.block_hash])
        node_a.chain.accept_block(fourth)

        node_b.receive(
            GossipEnvelope(
                kind="finality-evidence",
                origin="node-a",
                payload={
                    "checkpoint": checkpoint,
                    "certificate": certificate,
                    "finalized_block_hashes": finalized_hashes,
                    "frontier": [fourth.block_hash],
                },
                ttl=4,
            )
        )
        node_b.process_inbox()

        self.assertIn(checkpoint_id, node_b.verified_finality_evidence)
        self.assertEqual(node_b.outbox[-1].kind, "sync-request")
        self.assertEqual(node_b.outbox[-1].payload["block_hashes"], [fourth.block_hash])

    def test_three_node_block_broadcast_converges(self) -> None:
        producer = Wallet("producer-a", "producer-a-seed")
        node_a = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_b = PoCTNode("node-b", chain=Blockchain(difficulty=1, allow_new_producers=True))
        node_c = PoCTNode("node-c", chain=Blockchain(difficulty=1, allow_new_producers=True))

        node_a.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))
        node_b.add_peer(PeerInfo(node_id="node-a", endpoint="local-spool"))
        node_b.add_peer(PeerInfo(node_id="node-c", endpoint="local-spool"))
        node_c.add_peer(PeerInfo(node_id="node-b", endpoint="local-spool"))

        block = node_a.produce_block(producer.address)

        with tempfile.TemporaryDirectory() as tmpdir:
            node_a.write_envelopes(tmpdir)
            node_b.read_envelopes(tmpdir)
            node_b.process_inbox()
            node_b.write_envelopes(tmpdir)
            node_c.read_envelopes(tmpdir)
            node_c.process_inbox()

        self.assertIn(block.block_hash, node_b.chain.block_by_hash)
        self.assertIn(block.block_hash, node_c.chain.block_by_hash)
        self.assertTrue(node_b.has_converged_with_peer(node_a.sync_summary()))
        self.assertTrue(node_c.has_converged_with_peer(node_a.sync_summary()))

    def test_wallet_save_and_load_round_trip(self) -> None:
        wallet = Wallet.create("alice", seed="alice-seed")
        with tempfile.TemporaryDirectory() as tmpdir:
            path = wallet.save(Path(tmpdir) / "alice.json")
            restored = Wallet.load(path)
        self.assertEqual(restored.name, wallet.name)
        self.assertEqual(restored.mnemonic, wallet.mnemonic)
        self.assertEqual(restored.address, wallet.address)

    def test_render_wallet_page_contains_address_and_balance(self) -> None:
        chain = Blockchain(difficulty=1, allow_new_producers=True)
        wallet = Wallet.create("alice", seed="alice-seed")
        chain.faucet(wallet.address, 9)
        page = render_wallet_page(chain, wallet)
        self.assertIn(wallet.address, page)
        self.assertIn("9", page)
        self.assertIn("Mnemonic", page)

    def test_gossip_envelope_forward_decrements_ttl(self) -> None:
        envelope = GossipEnvelope(kind="block", origin="node-a", payload={"block_hash": "abc"}, ttl=3)
        forwarded = envelope.forward("node-b")
        self.assertEqual(forwarded.ttl, 2)
        self.assertEqual(forwarded.metadata["forwarded_by"], "node-b")

    def test_mock_zk_backend_round_trip(self) -> None:
        backend = MockZKBackend()
        proof = backend.prove(
            circuit_id="trajectory-validity",
            witness={"secret": 1},
            public_inputs={"txid": "abc"},
        )
        self.assertTrue(backend.verify(proof))

    def test_simple_l1_executor_applies_batch(self) -> None:
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
        chain.faucet(alice.address, 20)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=5, allowed_recipients=[bob.address])

        chain._identity_state(prod_a.address).phase = "mature"
        chain._identity_state(prod_a.address).compliant_txs = 30
        chain._identity_state(prod_b.address).phase = "mature"
        chain._identity_state(prod_b.address).compliant_txs = 30

        tx = chain.build_transaction(alice.key, [(bob.address, 5)], policy, timestamp=100)
        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(prod_b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)

        executor = SimpleL1Executor()
        checkpoint = executor.apply_batch(chain.confirmed_l1_batch())
        self.assertEqual(executor.accounts[bob.address], 5)
        self.assertEqual(checkpoint.tx_count, len(chain.confirmed_l1_batch()["transactions"]))

    def test_simple_l1_executor_applies_handoff(self) -> None:
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
        chain.faucet(alice.address, 20)
        policy = PolicyCommitment.from_values(epsilon=10.0, max_amount=5, allowed_recipients=[bob.address])

        for producer in (prod_a, prod_b, prod_c):
            chain._identity_state(producer.address).phase = "mature"
            chain._identity_state(producer.address).compliant_txs = 30

        tx = chain.build_transaction(alice.key, [(bob.address, 5)], policy, timestamp=100)
        parent = chain.blocks[-1].block_hash
        block_a = chain.build_candidate_block(prod_a.address, transactions=[tx], parents=[parent])
        chain.accept_block(block_a)
        block_b = chain.build_candidate_block(prod_b.address, transactions=[], parents=[block_a.block_hash])
        chain.accept_block(block_b)
        block_c = chain.build_candidate_block(prod_c.address, transactions=[], parents=[block_b.block_hash])
        chain.accept_block(block_c)

        executor = SimpleL1Executor()
        checkpoint = executor.apply_handoff(chain.export_l1_handoff())

        self.assertEqual(executor.accounts[bob.address], 5)
        self.assertEqual(checkpoint.tx_count, len(chain.export_l1_handoff()["batch"]["transactions"]))

    def test_load_generator_builds_transactions(self) -> None:
        chain = Blockchain(difficulty=1, producer_reward=5, allow_new_producers=True)
        alice = Wallet("alice", "alice-seed")
        bob = Wallet("bob", "bob-seed")
        chain.faucet(alice.address, 10)
        loadgen = LoadGenerator(chain)

        txs = loadgen.build_transactions(
            [
                AgentSpec(wallet=alice, recipients=[bob.address], amount=3),
            ],
            timestamp=100,
        )

        self.assertEqual(len(txs), 1)
        self.assertEqual(txs[0].outputs[0].recipient, bob.address)

    def test_cli_wallet_create_and_show(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            wallet_path = Path(tmpdir) / "alice.json"
            create = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "wallet-create",
                    "--name",
                    "alice",
                    "--seed",
                    "alice-seed",
                    "--path",
                    str(wallet_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"saved_to\"", create.stdout)
            show = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "wallet-show",
                    "--path",
                    str(wallet_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"wallet\"", show.stdout)
            self.assertIn("\"mnemonic\"", show.stdout)
            address = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "wallet-address",
                    "--path",
                    str(wallet_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"address\"", address.stdout)

    def test_cli_local_chain_flow(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            alice_wallet = Path(tmpdir) / "alice.json"
            bob_wallet = Path(tmpdir) / "bob.json"
            producer_wallet = Path(tmpdir) / "producer.json"
            cwd = Path(__file__).resolve().parents[1]

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "init",
                    "--path",
                    str(state_path),
                    "--allow-new-producers",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            for name, wallet_path, seed in (
                ("alice", alice_wallet, "alice-seed"),
                ("bob", bob_wallet, "bob-seed"),
                ("producer", producer_wallet, "producer-seed"),
            ):
                subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "structural_crypto.app.cli",
                        "wallet-create",
                        "--name",
                        name,
                        "--seed",
                        seed,
                        "--path",
                        str(wallet_path),
                    ],
                    cwd=cwd,
                    capture_output=True,
                    text=True,
                    check=True,
                )

            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "faucet",
                    "--path",
                    str(state_path),
                    "--wallet-path",
                    str(alice_wallet),
                    "--amount",
                    "20",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            send = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "send",
                    "--path",
                    str(state_path),
                    "--wallet-path",
                    str(alice_wallet),
                    "--to",
                    Wallet.load(bob_wallet).address,
                    "--amount",
                    "5",
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"mempool_size\": 1", send.stdout)
            produce = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "produce",
                    "--path",
                    str(state_path),
                    "--wallet-path",
                    str(producer_wallet),
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"block_hash\"", produce.stdout)
            balance = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "balance",
                    "--path",
                    str(state_path),
                    "--wallet-path",
                    str(bob_wallet),
                ],
                cwd=cwd,
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"balance\": 5", balance.stdout)

    def test_cli_init_accepts_emission_schedule(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            init = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "init",
                    "--path",
                    str(state_path),
                    "--allow-new-producers",
                    "--emission-stage",
                    "1:10",
                    "--emission-stage",
                    "3:5",
                    "--tail-reward-floor",
                    "1",
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"saved_to\"", init.stdout)
            chain = Blockchain.load_state(state_path)
            self.assertEqual(chain.reward_amount_for_block(1), 10.0)
            self.assertEqual(chain.reward_amount_for_block(3), 5.0)
            self.assertEqual(chain.tail_reward_floor, 1.0)

    def test_cli_show_dagknight_exposes_summary(self) -> None:
        import subprocess
        import sys

        with tempfile.TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "chain.json"
            chain = Blockchain(difficulty=1, allow_new_producers=True)
            a = Wallet("a", "a-seed")
            b = Wallet("b", "b-seed")
            chain._identity_state(a.address).phase = "mature"
            chain._identity_state(a.address).compliant_txs = 30
            chain._identity_state(b.address).phase = "mature"
            chain._identity_state(b.address).compliant_txs = 30
            parent = chain.blocks[-1].block_hash
            chain.accept_block(chain.build_candidate_block(a.address, transactions=[], parents=[parent]))
            chain.accept_block(chain.build_candidate_block(b.address, transactions=[], parents=[parent]))
            chain.save_state(state_path)

            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "structural_crypto.app.cli",
                    "show-dagknight",
                    "--path",
                    str(state_path),
                ],
                cwd=Path(__file__).resolve().parents[1],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertIn("\"dynamic_k\"", result.stdout)
            self.assertIn("\"blue_set\"", result.stdout)
            self.assertIn("\"weighted_anticone\"", result.stdout)
