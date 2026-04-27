"""Headless PoCT node skeleton for local multi-node testing."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from structural_crypto.ledger import Blockchain, Block, Transaction

from .p2p import GossipEnvelope, PeerInfo
from .rpc import RPCRequest, RPCResponse


@dataclass
class PoCTNode:
    SCHEMA_VERSION = 1

    node_id: str
    chain: Blockchain = field(default_factory=Blockchain)
    peers: Dict[str, PeerInfo] = field(default_factory=dict)
    inbox: List[GossipEnvelope] = field(default_factory=list)
    outbox: List[GossipEnvelope] = field(default_factory=list)
    seen_envelopes: set[str] = field(default_factory=set)
    spool_sequence: int = 0

    def add_peer(self, peer: PeerInfo) -> None:
        self.peers[peer.node_id] = peer

    def submit_transaction(self, tx: Transaction, signer_seed: str) -> None:
        self.chain.add_transaction(tx, signer_seed=signer_seed)
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="transaction",
                    origin=self.node_id,
                    payload={
                        "txid": tx.txid,
                        "tx": self.chain._transaction_to_dict(tx),
                        "signer_seed": signer_seed,
                    },
                )
            )
        )

    def produce_block(self, producer_id: str) -> Block:
        block = self.chain.produce_block(producer_id)
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="block",
                    origin=self.node_id,
                    payload={
                        "block_hash": block.block_hash,
                        "block": self.chain._block_to_dict(block),
                    },
                )
            )
        )
        return block

    def announce_sync_summary(self) -> None:
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="sync-summary",
                    origin=self.node_id,
                    payload=self.sync_summary(),
                )
            )
        )

    def request_missing_blocks(self, peer_node_id: str, block_hashes: List[str]) -> None:
        if not block_hashes:
            return
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="sync-request",
                    origin=self.node_id,
                    payload={"block_hashes": list(block_hashes)},
                    metadata={"target_peer_id": peer_node_id},
                )
            )
        )

    def send_block_to_peer(self, peer_node_id: str, block_hash: str) -> None:
        if block_hash not in self.chain.block_by_hash:
            return
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="block",
                    origin=self.node_id,
                    payload={
                        "block_hash": block_hash,
                        "block": self.export_block(block_hash),
                    },
                    metadata={"target_peer_id": peer_node_id},
                )
            )
        )

    def accept_block(self, block: Block) -> None:
        self.chain.accept_block(block)

    def receive(self, envelope: GossipEnvelope) -> None:
        normalized = self._normalize_envelope(envelope)
        envelope_id = self._envelope_id(normalized)
        if normalized.ttl <= 0 or envelope_id in self.seen_envelopes:
            return
        self.seen_envelopes.add(envelope_id)
        self.inbox.append(normalized)

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
            "config_digest": self.chain.config_digest(),
            "consensus_digest": self.chain.consensus_digest(),
            "state_digest": self.chain.state_digest(),
            "known_block_count": len(self.chain.block_by_hash),
            "frontier": list(self.chain.frontier),
            "virtual_order": self.chain.virtual_order(),
            "confirmed_order": self.chain.confirmed_order(),
        }

    def export_l1_feed(self, confirmed_only: bool = True) -> dict:
        return self.chain.export_l1_feed(confirmed_only=confirmed_only)

    def frontier_summary(self) -> dict:
        return {
            "node_id": self.node_id,
            "config_digest": self.chain.config_digest(),
            "consensus_digest": self.chain.consensus_digest(),
            "state_digest": self.chain.state_digest(),
            "frontier": list(self.chain.frontier),
            "known_blocks": list(self.chain.block_by_hash.keys()),
            "confirmed_order": self.chain.confirmed_order(),
        }

    def compare_sync_summary(self, peer_summary: dict) -> dict:
        local_summary = self.sync_summary()
        peer_frontier = sorted(peer_summary.get("frontier", []))
        peer_virtual = peer_summary.get("virtual_order", [])
        peer_confirmed = peer_summary.get("confirmed_order", [])
        config_match = peer_summary.get("config_digest") == local_summary["config_digest"]
        consensus_match = peer_summary.get("consensus_digest") == local_summary["consensus_digest"]
        state_match = peer_summary.get("state_digest") == local_summary["state_digest"]
        frontier_match = peer_frontier == sorted(local_summary["frontier"])
        virtual_match = peer_virtual == local_summary["virtual_order"] if peer_virtual else False
        confirmed_match = peer_confirmed == local_summary["confirmed_order"]
        missing = self.sync_frontier_from_peer(peer_summary)
        return {
            "config_match": config_match,
            "consensus_match": consensus_match,
            "state_match": state_match,
            "frontier_match": frontier_match,
            "virtual_order_match": virtual_match,
            "confirmed_order_match": confirmed_match,
            "missing_blocks": missing,
            "comparable": config_match,
            "converged": config_match and consensus_match and frontier_match and confirmed_match and virtual_match,
        }

    def has_converged_with_peer(self, peer_summary: dict) -> bool:
        return self.compare_sync_summary(peer_summary)["converged"]

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
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        temp_target = target.with_name(f"{target.name}.tmp")
        temp_target.write_text(self.export_state_json(), encoding="utf-8")
        os.replace(temp_target, target)
        return target

    @classmethod
    def load(cls, node_id: str, path: str | Path) -> "PoCTNode":
        source = Path(path)
        state = json.loads(source.read_text(encoding="utf-8"))
        if "chain" not in state:
            return cls(node_id=node_id, chain=Blockchain.from_state(state))
        if state.get("schema_version") != cls.SCHEMA_VERSION:
            raise ValueError(
                f"unsupported node schema version: {state.get('schema_version')!r}, expected {cls.SCHEMA_VERSION}"
            )
        node = cls(node_id=state.get("node_id", node_id), chain=Blockchain.from_state(state["chain"]))
        node.peers = {
            item["node_id"]: PeerInfo(**item)
            for item in state.get("peers", [])
        }
        node.inbox = [node._envelope_from_dict(item) for item in state.get("inbox", [])]
        node.outbox = [node._envelope_from_dict(item) for item in state.get("outbox", [])]
        node.seen_envelopes = set(state.get("seen_envelopes", []))
        node.spool_sequence = int(state.get("spool_sequence", 0))
        return node

    def export_state(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "node_id": self.node_id,
            "chain": self.chain.export_state(),
            "peers": [
                {
                    "node_id": peer.node_id,
                    "endpoint": peer.endpoint,
                    "role": peer.role,
                }
                for peer in self.peers.values()
            ],
            "inbox": [self._envelope_to_dict(item) for item in self.inbox],
            "outbox": [self._envelope_to_dict(item) for item in self.outbox],
            "seen_envelopes": sorted(self.seen_envelopes),
            "spool_sequence": self.spool_sequence,
        }

    def export_state_json(self) -> str:
        return json.dumps(self.export_state(), sort_keys=True, separators=(",", ":"))

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
        if request.method == "submit_tx":
            tx = self.chain._transaction_from_dict(request.params["tx"])
            self.submit_transaction(tx, signer_seed=request.params["signer_seed"])
            return RPCResponse(ok=True, result={"txid": tx.txid})
        if request.method == "get_l1_feed":
            confirmed_only = request.params.get("confirmed_only", True)
            return RPCResponse(ok=True, result=self.export_l1_feed(confirmed_only=confirmed_only))
        return RPCResponse(ok=False, error=f"unknown method: {request.method}")

    def write_envelopes(self, spool_dir: str | Path) -> int:
        base = Path(spool_dir)
        count = 0
        while self.outbox:
            envelope = self.outbox.pop(0)
            normalized = self._normalize_envelope(envelope)
            envelope_id = self._envelope_id(normalized)
            target_peer_id = normalized.metadata.get("target_peer_id")
            peer_ids = [target_peer_id] if target_peer_id else list(self.peers)
            for peer_id in peer_ids:
                if peer_id not in self.peers:
                    continue
                peer_dir = base / peer_id
                peer_dir.mkdir(parents=True, exist_ok=True)
                sequence = self.spool_sequence
                self.spool_sequence += 1
                file_path = peer_dir / f"{self.node_id}-{sequence:06d}-{normalized.kind}-{envelope_id[:12]}.json"
                temp_path = file_path.with_name(f".{file_path.name}.tmp")
                temp_path.write_text(
                    json.dumps(self._envelope_to_dict(normalized), sort_keys=True),
                    encoding="utf-8",
                )
                os.replace(temp_path, file_path)
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

    def fetch_missing_block_via_rpc(self, rpc_handler, block_hash: str) -> str | None:
        if block_hash in self.chain.block_by_hash:
            return block_hash
        response = rpc_handler(RPCRequest(method="get_block", params={"block_hash": block_hash}))
        if not response.ok:
            return None
        block_data = response.result["block"]
        for parent_hash in block_data["parents"]:
            if parent_hash not in self.chain.block_by_hash:
                fetched_parent = self.fetch_missing_block_via_rpc(rpc_handler, parent_hash)
                if fetched_parent is None:
                    return None
        self.import_block(block_data)
        return block_hash

    def reconcile_with_peer(self, rpc_handler) -> List[str]:
        response = rpc_handler(RPCRequest(method="get_sync_summary"))
        if not response.ok:
            return []
        missing = self.sync_frontier_from_peer(response.result)
        imported: List[str] = []
        for block_hash in missing:
            fetched = self.fetch_missing_block_via_rpc(rpc_handler, block_hash)
            if fetched is not None:
                imported.append(fetched)
        return imported

    def _handle_envelope(self, envelope: GossipEnvelope) -> None:
        if envelope.kind == "block" and "block" in envelope.payload:
            block_hash = envelope.payload.get("block_hash")
            before_known = block_hash in self.chain.block_by_hash if block_hash else False
            self.import_block(envelope.payload["block"])
            if not before_known and envelope.ttl > 1:
                self.outbox.append(self._normalize_envelope(envelope.forward(self.node_id)))
        if envelope.kind == "transaction" and "tx" in envelope.payload:
            tx = self.chain._transaction_from_dict(envelope.payload["tx"])
            signer_seed = envelope.payload["signer_seed"]
            if not any(existing.txid == tx.txid for existing in self.chain.mempool):
                self.chain.add_transaction(tx, signer_seed=signer_seed)
                if envelope.ttl > 1:
                    self.outbox.append(self._normalize_envelope(envelope.forward(self.node_id)))
        if envelope.kind == "sync-summary":
            missing = self.sync_frontier_from_peer(envelope.payload)
            if missing:
                self.request_missing_blocks(envelope.origin, missing)
        if envelope.kind == "sync-request":
            for block_hash in envelope.payload.get("block_hashes", []):
                self.send_block_to_peer(envelope.origin, block_hash)

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

    @staticmethod
    def _envelope_id(envelope: GossipEnvelope) -> str:
        if "envelope_id" in envelope.metadata:
            return str(envelope.metadata["envelope_id"])
        stable_data = {
            "kind": envelope.kind,
            "origin": envelope.origin,
            "payload": envelope.payload,
        }
        encoded = json.dumps(stable_data, sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @classmethod
    def _normalize_envelope(cls, envelope: GossipEnvelope) -> GossipEnvelope:
        metadata = dict(envelope.metadata)
        metadata.setdefault("envelope_id", cls._envelope_id(envelope))
        return GossipEnvelope(
            kind=envelope.kind,
            origin=envelope.origin,
            payload=dict(envelope.payload),
            ttl=envelope.ttl,
            metadata=metadata,
        )
