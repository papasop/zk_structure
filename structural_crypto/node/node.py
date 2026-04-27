"""Headless PoCT node skeleton for local multi-node testing."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from structural_crypto.ledger import Blockchain, Block, Transaction

from .p2p import GossipEnvelope, PeerInfo
from .rpc import RPCRequest, RPCResponse


@dataclass
class PoCTNode:
    node_id: str
    chain: Blockchain = field(default_factory=Blockchain)
    peers: Dict[str, PeerInfo] = field(default_factory=dict)
    inbox: List[GossipEnvelope] = field(default_factory=list)
    outbox: List[GossipEnvelope] = field(default_factory=list)

    def add_peer(self, peer: PeerInfo) -> None:
        self.peers[peer.node_id] = peer

    def submit_transaction(self, tx: Transaction, signer_seed: str) -> None:
        self.chain.add_transaction(tx, signer_seed=signer_seed)
        self.outbox.append(
            GossipEnvelope(
                kind="transaction",
                origin=self.node_id,
                payload={"txid": tx.txid},
            )
        )

    def produce_block(self, producer_id: str) -> Block:
        block = self.chain.produce_block(producer_id)
        self.outbox.append(
            GossipEnvelope(
                kind="block",
                origin=self.node_id,
                payload={
                    "block_hash": block.block_hash,
                    "block": self.chain._block_to_dict(block),
                },
            )
        )
        return block

    def accept_block(self, block: Block) -> None:
        self.chain.accept_block(block)

    def receive(self, envelope: GossipEnvelope) -> None:
        self.inbox.append(envelope)

    def process_inbox(self) -> int:
        processed = 0
        while self.inbox:
            envelope = self.inbox.pop(0)
            self._handle_envelope(envelope)
            processed += 1
        return processed

    def sync_summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "frontier": list(self.chain.frontier),
            "virtual_order": self.chain.virtual_order(),
            "confirmed_order": self.chain.confirmed_order(),
        }

    def export_l1_feed(self, confirmed_only: bool = True) -> dict:
        return self.chain.export_l1_feed(confirmed_only=confirmed_only)

    def frontier_summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "frontier": list(self.chain.frontier),
            "known_blocks": list(self.chain.block_by_hash.keys()),
            "confirmed_order": self.chain.confirmed_order(),
        }

    def sync_frontier_from_peer(self, peer_summary: dict) -> List[str]:
        peer_frontier = peer_summary.get("frontier", [])
        missing = [block_hash for block_hash in peer_frontier if block_hash not in self.chain.block_by_hash]
        return missing

    def export_block(self, block_hash: str) -> dict:
        block = self.chain.block_by_hash[block_hash]
        return self.chain._block_to_dict(block)

    def import_block(self, block_data: dict) -> Block:
        block = self.chain._block_from_dict(block_data)
        if block.block_hash in self.chain.block_by_hash:
            return self.chain.block_by_hash[block.block_hash]
        self.accept_block(block)
        return block

    def save(self, path: str | Path) -> Path:
        return self.chain.save_state(path)

    @classmethod
    def load(cls, node_id: str, path: str | Path) -> "PoCTNode":
        return cls(node_id=node_id, chain=Blockchain.load_state(path))

    def handle_rpc(self, request: RPCRequest) -> RPCResponse:
        if request.method == "get_frontier":
            return RPCResponse(ok=True, result={"frontier": list(self.chain.frontier)})
        if request.method == "get_confirmed":
            return RPCResponse(ok=True, result={"confirmed_order": self.chain.confirmed_order()})
        if request.method == "get_sync_summary":
            return RPCResponse(ok=True, result=self.frontier_summary())
        if request.method == "get_block":
            block_hash = request.params["block_hash"]
            return RPCResponse(ok=True, result={"block": self.export_block(block_hash)})
        if request.method == "get_l1_feed":
            confirmed_only = request.params.get("confirmed_only", True)
            return RPCResponse(ok=True, result=self.export_l1_feed(confirmed_only=confirmed_only))
        return RPCResponse(ok=False, error=f"unknown method: {request.method}")

    def write_envelopes(self, spool_dir: str | Path) -> int:
        base = Path(spool_dir)
        count = 0
        while self.outbox:
            envelope = self.outbox.pop(0)
            for peer_id in self.peers:
                peer_dir = base / peer_id
                peer_dir.mkdir(parents=True, exist_ok=True)
                file_path = peer_dir / f"{self.node_id}-{count:06d}-{envelope.kind}.json"
                file_path.write_text(
                    json.dumps(self._envelope_to_dict(envelope), sort_keys=True),
                    encoding="utf-8",
                )
                count += 1
        return count

    def read_envelopes(self, spool_dir: str | Path) -> int:
        node_dir = Path(spool_dir) / self.node_id
        if not node_dir.exists():
            return 0
        processed = 0
        for path in sorted(node_dir.glob("*.json")):
            data = json.loads(path.read_text(encoding="utf-8"))
            self.receive(self._envelope_from_dict(data))
            path.unlink()
            processed += 1
        return processed

    def sync_blocks_from_peer(self, peer: "PoCTNode") -> List[str]:
        missing = self.sync_frontier_from_peer(peer.frontier_summary())
        imported: List[str] = []
        while missing:
            block_hash = missing.pop(0)
            if block_hash in self.chain.block_by_hash:
                continue
            block_data = peer.export_block(block_hash)
            for parent_hash in block_data["parents"]:
                if parent_hash not in self.chain.block_by_hash:
                    missing.append(parent_hash)
            self.import_block(block_data)
            imported.append(block_hash)
        return imported

    def _handle_envelope(self, envelope: GossipEnvelope) -> None:
        if envelope.kind == "block" and "block" in envelope.payload:
            self.import_block(envelope.payload["block"])
        if envelope.kind == "sync-summary":
            self.sync_frontier_from_peer(envelope.payload)

    @staticmethod
    def _envelope_to_dict(envelope: GossipEnvelope) -> dict:
        return {
            "kind": envelope.kind,
            "origin": envelope.origin,
            "payload": envelope.payload,
            "ttl": envelope.ttl,
            "metadata": envelope.metadata,
        }

    @staticmethod
    def _envelope_from_dict(data: dict) -> GossipEnvelope:
        return GossipEnvelope(
            kind=data["kind"],
            origin=data["origin"],
            payload=data["payload"],
            ttl=data.get("ttl", 8),
            metadata=data.get("metadata", {}),
        )
