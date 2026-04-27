"""Headless PoCT node skeleton for local multi-node testing."""

from __future__ import annotations

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
                payload={"block_hash": block.block_hash},
            )
        )
        return block

    def accept_block(self, block: Block) -> None:
        self.chain.accept_block(block)

    def receive(self, envelope: GossipEnvelope) -> None:
        self.inbox.append(envelope)

    def sync_summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "frontier": list(self.chain.frontier),
            "virtual_order": self.chain.virtual_order(),
            "confirmed_order": self.chain.confirmed_order(),
        }

    def export_l1_feed(self, confirmed_only: bool = True) -> dict:
        return self.chain.export_l1_feed(confirmed_only=confirmed_only)

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
        if request.method == "get_l1_feed":
            confirmed_only = request.params.get("confirmed_only", True)
            return RPCResponse(ok=True, result=self.export_l1_feed(confirmed_only=confirmed_only))
        return RPCResponse(ok=False, error=f"unknown method: {request.method}")
