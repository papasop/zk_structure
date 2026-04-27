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
from structural_crypto.node.rpc import RPCRequest
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
    def test_node_sync_summary_and_rpc(self) -> None:
        node = PoCTNode("node-a", chain=Blockchain(difficulty=1, allow_new_producers=True))
        peer = PeerInfo(node_id="node-b", endpoint="127.0.0.1:9001")
        node.add_peer(peer)

        summary = node.sync_summary()
        self.assertEqual(summary["node_id"], "node-a")
        response = node.handle_rpc(RPCRequest(method="get_frontier"))
        self.assertTrue(response.ok)
        self.assertIn("frontier", response.result)

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
