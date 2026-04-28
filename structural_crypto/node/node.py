"""Headless PoCT node skeleton for local multi-node testing."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from structural_crypto.ledger import Blockchain, Block, FinalityVote, Transaction

from .p2p import GossipEnvelope, PeerInfo
from .rpc import RPCRequest, RPCResponse


@dataclass
class PoCTNode:
    SCHEMA_VERSION = 2

    node_id: str
    chain: Blockchain = field(default_factory=Blockchain)
    finality_voter_id: Optional[str] = None
    peers: Dict[str, PeerInfo] = field(default_factory=dict)
    inbox: List[GossipEnvelope] = field(default_factory=list)
    outbox: List[GossipEnvelope] = field(default_factory=list)
    seen_envelopes: set[str] = field(default_factory=set)
    verified_finality_evidence: Dict[str, dict] = field(default_factory=dict)
    finality_votes: Dict[str, Dict[str, dict]] = field(default_factory=dict)
    finality_certificates: Dict[str, dict] = field(default_factory=dict)
    finality_conflicts: List[dict] = field(default_factory=list)
    adopted_finality_checkpoint_id: Optional[str] = None
    current_finality_round: int = 0
    current_finality_checkpoint_id: Optional[str] = None
    finality_timeout_ticks: int = 0
    finality_timeout_limit: int = 3
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

    def announce_finality_summary(self) -> None:
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="finality-summary",
                    origin=self.node_id,
                    payload=self.finality_summary(),
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

    def request_finality_evidence(self, peer_node_id: str, checkpoint_id: str) -> None:
        if not checkpoint_id:
            return
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="finality-request",
                    origin=self.node_id,
                    payload={"checkpoint_id": checkpoint_id},
                    metadata={"target_peer_id": peer_node_id},
                )
            )
        )

    def send_finality_evidence_to_peer(self, peer_node_id: str, checkpoint_id: str) -> None:
        finality_state = self.chain.export_finality_state()
        checkpoint = next(
            (item for item in finality_state["checkpoints"] if item["checkpoint_id"] == checkpoint_id),
            None,
        )
        if checkpoint is None:
            return
        certificate = checkpoint.get("finalize_certificate") or checkpoint.get("lock_certificate")
        if certificate is None:
            return
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="finality-evidence",
                    origin=self.node_id,
                    payload={
                        "checkpoint": checkpoint,
                        "certificate": certificate,
                        "finalized_block_hashes": self.chain.finalized_l1_batch()["block_hashes"],
                        "frontier": list(self.chain.frontier),
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
        finality = self.finality_summary()
        return {
            "node_id": self.node_id,
            "config_digest": self.chain.config_digest(),
            "consensus_digest": self.chain.consensus_digest(),
            "state_digest": self.chain.state_digest(),
            "known_block_count": len(self.chain.block_by_hash),
            "frontier": list(self.chain.frontier),
            "virtual_order": self.chain.virtual_order(),
            "confirmed_order": self.chain.confirmed_order(),
            "finality": finality,
            "finalized_order": finality["finalized_order"],
        }

    def export_l1_feed(self, confirmed_only: bool = True) -> dict:
        return self.chain.export_l1_feed(confirmed_only=confirmed_only)

    def export_finalized_l1_feed(self) -> dict:
        return self.chain.finalized_l1_batch()

    def export_l1_handoff(self, prefer_finalized: bool = True) -> dict:
        return self.chain.export_l1_handoff(prefer_finalized=prefer_finalized)

    def dagknight_summary(self) -> dict:
        return self.chain.dagknight_summary()

    def finality_summary(self) -> dict:
        self._ensure_current_finality_round()
        summary = self.chain.finality_summary()
        summary["node_id"] = self.node_id
        summary["adopted_finalized_checkpoint"] = self.adopted_finality_checkpoint_id
        summary["current_finality_round"] = self.current_finality_round
        summary["current_finality_checkpoint_id"] = self.current_finality_checkpoint_id
        summary["finality_timeout_ticks"] = self.finality_timeout_ticks
        summary["finality_timeout_limit"] = self.finality_timeout_limit
        summary["finality_conflict_count"] = len(self.finality_conflicts)
        return summary

    def cast_finality_vote(self, checkpoint_id: str | None = None) -> dict | None:
        self._ensure_current_finality_round()
        checkpoint = self._checkpoint_dict(checkpoint_id)
        if checkpoint is None:
            return None
        if checkpoint_id is None and self.current_finality_checkpoint_id is not None:
            checkpoint = self._checkpoint_dict(self.current_finality_checkpoint_id)
            if checkpoint is None:
                return None
        voter_id = self.finality_voter_id or self.node_id
        weight_map = self.chain.finality_weight_map()
        voter_weight = weight_map.get(voter_id)
        if voter_weight is None or voter_weight <= 0.0:
            return None
        vote = {
            "epoch": checkpoint["epoch"],
            "round": checkpoint["round"],
            "vote_type": "lock",
            "checkpoint_id": checkpoint["checkpoint_id"],
            "committee_digest": checkpoint["committee_digest"],
            "voter_id": voter_id,
            "voter_weight": voter_weight,
            "vote_digest": self.chain._finality_vote_digest(
                epoch=checkpoint["epoch"],
                round_index=checkpoint["round"],
                vote_type="lock",
                checkpoint_id=checkpoint["checkpoint_id"],
                committee_digest=checkpoint["committee_digest"],
                voter_id=voter_id,
                voter_weight=voter_weight,
            ),
        }
        if not self._record_finality_vote(checkpoint, vote):
            return None
        self.current_finality_round = checkpoint["round"]
        self.current_finality_checkpoint_id = checkpoint["checkpoint_id"]
        self.finality_timeout_ticks = 0
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="finality-vote",
                    origin=self.node_id,
                    payload={"checkpoint": checkpoint, "vote": vote},
                )
            )
        )
        return vote

    def advance_finality_round(self, force: bool = False) -> dict | None:
        self._ensure_current_finality_round()
        checkpoints = self.chain.export_finality_state()["checkpoints"]
        if not checkpoints:
            self.current_finality_round = 0
            self.current_finality_checkpoint_id = None
            return None
        checkpoint_by_round = {item["round"]: item for item in checkpoints}
        latest_round = checkpoints[-1]["round"]
        target_round = self.current_finality_round
        if target_round <= 0:
            target_round = 1
        current_checkpoint = checkpoint_by_round.get(target_round)
        if current_checkpoint is None:
            target_round = min(max(1, target_round), latest_round)
            current_checkpoint = checkpoint_by_round.get(target_round)
        if current_checkpoint is None:
            return None
        should_advance = force or current_checkpoint["checkpoint_id"] in self.finality_certificates
        if not should_advance and current_checkpoint["round"] > 1:
            previous_checkpoint = checkpoint_by_round.get(current_checkpoint["round"] - 1)
            if previous_checkpoint is not None and previous_checkpoint["checkpoint_id"] in self.verified_finality_evidence:
                should_advance = True
        if should_advance and target_round < latest_round:
            target_round += 1
            current_checkpoint = checkpoint_by_round[target_round]
        self.current_finality_round = current_checkpoint["round"]
        self.current_finality_checkpoint_id = current_checkpoint["checkpoint_id"]
        self.finality_timeout_ticks = 0
        return dict(current_checkpoint)

    def timeout_tick(self) -> dict:
        self._ensure_current_finality_round()
        checkpoint = self._checkpoint_dict(self.current_finality_checkpoint_id)
        if checkpoint is None:
            return {"timed_out": False, "reason": "no-checkpoint"}
        checkpoint_votes = self.finality_votes.get(checkpoint["checkpoint_id"], {})
        has_quorum = checkpoint["checkpoint_id"] in self.finality_certificates
        if has_quorum:
            advanced = self.advance_finality_round(force=False)
            return {
                "timed_out": False,
                "reason": "quorum-reached",
                "advanced_to_round": advanced["round"] if advanced is not None else self.current_finality_round,
            }
        self.finality_timeout_ticks += 1
        if self.finality_timeout_ticks < self.finality_timeout_limit:
            return {
                "timed_out": False,
                "reason": "waiting",
                "timeout_ticks": self.finality_timeout_ticks,
                "vote_count": len(checkpoint_votes),
            }
        self.finality_timeout_ticks = 0
        vote = self.cast_finality_vote(checkpoint["checkpoint_id"])
        if vote is not None:
            return {
                "timed_out": True,
                "reason": "retry-vote",
                "checkpoint_id": checkpoint["checkpoint_id"],
                "round": checkpoint["round"],
                "vote_digest": vote["vote_digest"],
            }
        advanced = self.advance_finality_round(force=True)
        return {
            "timed_out": True,
            "reason": "advance-round",
            "advanced_to_round": advanced["round"] if advanced is not None else self.current_finality_round,
            "checkpoint_id": self.current_finality_checkpoint_id,
        }

    def frontier_summary(self) -> dict:
        finality = self.finality_summary()
        return {
            "node_id": self.node_id,
            "config_digest": self.chain.config_digest(),
            "consensus_digest": self.chain.consensus_digest(),
            "state_digest": self.chain.state_digest(),
            "frontier": list(self.chain.frontier),
            "known_blocks": list(self.chain.block_by_hash.keys()),
            "confirmed_order": self.chain.confirmed_order(),
            "finality": finality,
            "finalized_order": finality["finalized_order"],
        }

    def compare_sync_summary(self, peer_summary: dict) -> dict:
        local_summary = self.sync_summary()
        peer_frontier = sorted(peer_summary.get("frontier", []))
        peer_virtual = peer_summary.get("virtual_order", [])
        peer_confirmed = peer_summary.get("confirmed_order", [])
        peer_finality = peer_summary.get("finality", {})
        config_match = peer_summary.get("config_digest") == local_summary["config_digest"]
        consensus_match = peer_summary.get("consensus_digest") == local_summary["consensus_digest"]
        state_match = peer_summary.get("state_digest") == local_summary["state_digest"]
        frontier_match = peer_frontier == sorted(local_summary["frontier"])
        virtual_match = peer_virtual == local_summary["virtual_order"] if peer_virtual else False
        confirmed_match = peer_confirmed == local_summary["confirmed_order"]
        finalized_match = peer_finality.get("finalized_prefix_digest") == local_summary["finality"].get(
            "finalized_prefix_digest"
        )
        committee_match = peer_finality.get("committee_digest") == local_summary["finality"].get("committee_digest")
        missing = self.sync_frontier_from_peer(peer_summary)
        return {
            "config_match": config_match,
            "consensus_match": consensus_match,
            "state_match": state_match,
            "frontier_match": frontier_match,
            "virtual_order_match": virtual_match,
            "confirmed_order_match": confirmed_match,
            "finalized_order_match": finalized_match,
            "committee_match": committee_match,
            "missing_blocks": missing,
            "comparable": config_match,
            "converged": (
                config_match
                and consensus_match
                and frontier_match
                and confirmed_match
                and virtual_match
                and finalized_match
                and committee_match
            ),
        }

    def has_converged_with_peer(self, peer_summary: dict) -> bool:
        return self.compare_sync_summary(peer_summary)["converged"]

    def compare_finality_summary(self, peer_summary: dict) -> dict:
        local_summary = self.finality_summary()
        config_match = peer_summary.get("config_digest", self.chain.config_digest()) == self.chain.config_digest()
        committee_match = peer_summary.get("committee_digest") == local_summary["committee_digest"]
        finalized_checkpoint_match = (
            peer_summary.get("latest_finalized_checkpoint") == local_summary["latest_finalized_checkpoint"]
        )
        finalized_prefix_match = peer_summary.get("finalized_prefix_digest") == local_summary["finalized_prefix_digest"]
        return {
            "config_match": config_match,
            "committee_match": committee_match,
            "finalized_checkpoint_match": finalized_checkpoint_match,
            "finalized_prefix_match": finalized_prefix_match,
            "converged": (
                config_match and committee_match and finalized_checkpoint_match and finalized_prefix_match
            ),
        }

    def finalized_blocks_missing_locally(self, block_hashes: List[str]) -> List[str]:
        return [block_hash for block_hash in block_hashes if block_hash not in self.chain.block_by_hash]

    def verify_and_store_finality_evidence(self, checkpoint: dict, certificate: dict) -> bool:
        if self._certificate_conflict(checkpoint, certificate) is not None:
            return False
        if not self.chain.verify_finality_evidence(checkpoint, certificate):
            return False
        checkpoint_id = checkpoint["checkpoint_id"]
        self.verified_finality_evidence[checkpoint_id] = {
            "checkpoint": dict(checkpoint),
            "certificate": dict(certificate),
        }
        self.adopted_finality_checkpoint_id = checkpoint_id
        self.advance_finality_round(force=False)
        return True

    def verify_and_store_live_finality_certificate(self, checkpoint: dict, certificate: dict) -> bool:
        if self._certificate_conflict(checkpoint, certificate) is not None:
            return False
        if not self.chain.verify_external_finality_certificate(checkpoint, certificate):
            return False
        checkpoint_id = checkpoint["checkpoint_id"]
        self.finality_certificates[checkpoint_id] = {
            "checkpoint": dict(checkpoint),
            "certificate": dict(certificate),
        }
        if certificate.get("vote_type") == "finalize":
            self.verified_finality_evidence[checkpoint_id] = {
                "checkpoint": dict(checkpoint),
                "certificate": dict(certificate),
            }
            self.adopted_finality_checkpoint_id = checkpoint_id
            self.advance_finality_round(force=False)
        return True

    def reconcile_finality_with_peer(self, rpc_handler) -> dict:
        summary_response = rpc_handler(RPCRequest(method="get_finality_summary"))
        if not summary_response.ok:
            return {"verified": False, "reason": "summary-unavailable"}
        summary = summary_response.result
        checkpoint_id = summary.get("latest_finalized_checkpoint")
        if checkpoint_id is None:
            return {"verified": True, "checkpoint_id": None}
        batch_response = rpc_handler(RPCRequest(method="get_finalized_batch"))
        finalized_block_hashes = list(batch_response.result.get("block_hashes", [])) if batch_response.ok else []
        imported: List[str] = []
        for block_hash in finalized_block_hashes:
            fetched = self.fetch_missing_block_via_rpc(rpc_handler, block_hash)
            if fetched is not None and fetched not in imported:
                imported.append(fetched)
        sync_response = rpc_handler(RPCRequest(method="get_sync_summary"))
        if sync_response.ok:
            for block_hash in self.sync_frontier_from_peer(sync_response.result):
                fetched = self.fetch_missing_block_via_rpc(rpc_handler, block_hash)
                if fetched is not None and fetched not in imported:
                    imported.append(fetched)
        checkpoint_response = rpc_handler(RPCRequest(method="get_checkpoint", params={"checkpoint_id": checkpoint_id}))
        certificate_response = rpc_handler(
            RPCRequest(method="get_certificate", params={"checkpoint_id": checkpoint_id})
        )
        if not checkpoint_response.ok or not certificate_response.ok:
            return {"verified": False, "reason": "evidence-unavailable", "checkpoint_id": checkpoint_id}
        verified = self.verify_and_store_finality_evidence(
            checkpoint_response.result["checkpoint"],
            certificate_response.result["certificate"],
        )
        return {
            "verified": verified,
            "checkpoint_id": checkpoint_id,
            "finalized_block_hashes": finalized_block_hashes,
            "imported_finalized_blocks": imported,
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
        node = cls(
            node_id=state.get("node_id", node_id),
            chain=Blockchain.from_state(state["chain"]),
            finality_voter_id=state.get("finality_voter_id"),
        )
        node.peers = {
            item["node_id"]: PeerInfo(**item)
            for item in state.get("peers", [])
        }
        node.inbox = [node._envelope_from_dict(item) for item in state.get("inbox", [])]
        node.outbox = [node._envelope_from_dict(item) for item in state.get("outbox", [])]
        node.seen_envelopes = set(state.get("seen_envelopes", []))
        node.verified_finality_evidence = dict(state.get("verified_finality_evidence", {}))
        node.finality_votes = {
            checkpoint_id: dict(votes)
            for checkpoint_id, votes in state.get("finality_votes", {}).items()
        }
        node.finality_certificates = dict(state.get("finality_certificates", {}))
        node.finality_conflicts = list(state.get("finality_conflicts", []))
        node.adopted_finality_checkpoint_id = state.get("adopted_finality_checkpoint_id")
        node.current_finality_round = int(state.get("current_finality_round", 0))
        node.current_finality_checkpoint_id = state.get("current_finality_checkpoint_id")
        node.finality_timeout_ticks = int(state.get("finality_timeout_ticks", 0))
        node.finality_timeout_limit = int(state.get("finality_timeout_limit", 3))
        node.spool_sequence = int(state.get("spool_sequence", 0))
        node._ensure_current_finality_round()
        return node

    def export_state(self) -> dict:
        return {
            "schema_version": self.SCHEMA_VERSION,
            "node_id": self.node_id,
            "finality_voter_id": self.finality_voter_id,
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
            "verified_finality_evidence": dict(self.verified_finality_evidence),
            "finality_votes": {checkpoint_id: dict(votes) for checkpoint_id, votes in self.finality_votes.items()},
            "finality_certificates": dict(self.finality_certificates),
            "finality_conflicts": list(self.finality_conflicts),
            "adopted_finality_checkpoint_id": self.adopted_finality_checkpoint_id,
            "current_finality_round": self.current_finality_round,
            "current_finality_checkpoint_id": self.current_finality_checkpoint_id,
            "finality_timeout_ticks": self.finality_timeout_ticks,
            "finality_timeout_limit": self.finality_timeout_limit,
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
        if request.method == "get_finality_summary":
            return RPCResponse(ok=True, result=self.finality_summary())
        if request.method == "get_dagknight_summary":
            return RPCResponse(ok=True, result=self.dagknight_summary())
        if request.method == "get_committee":
            return RPCResponse(ok=True, result={"committee": self.chain.export_finality_state()["committee"]})
        if request.method == "get_checkpoint":
            checkpoint_id = request.params["checkpoint_id"]
            for checkpoint in self.chain.export_finality_state()["checkpoints"]:
                if checkpoint["checkpoint_id"] == checkpoint_id:
                    return RPCResponse(ok=True, result={"checkpoint": checkpoint})
            return RPCResponse(ok=False, error=f"unknown checkpoint: {checkpoint_id}")
        if request.method == "get_certificate":
            checkpoint_id = request.params["checkpoint_id"]
            if checkpoint_id in self.finality_certificates:
                return RPCResponse(ok=True, result={"certificate": self.finality_certificates[checkpoint_id]["certificate"]})
            for checkpoint in self.chain.export_finality_state()["checkpoints"]:
                if checkpoint["checkpoint_id"] != checkpoint_id:
                    continue
                certificate = checkpoint.get("finalize_certificate") or checkpoint.get("lock_certificate")
                if certificate is None:
                    return RPCResponse(ok=False, error=f"checkpoint has no certificate: {checkpoint_id}")
                return RPCResponse(ok=True, result={"certificate": certificate})
            return RPCResponse(ok=False, error=f"unknown checkpoint: {checkpoint_id}")
        if request.method == "cast_finality_vote":
            checkpoint_id = request.params.get("checkpoint_id")
            vote = self.cast_finality_vote(checkpoint_id=checkpoint_id)
            if vote is None:
                return RPCResponse(ok=False, error="vote-unavailable")
            return RPCResponse(ok=True, result={"vote": vote})
        if request.method == "advance_finality_round":
            checkpoint = self.advance_finality_round(force=request.params.get("force", False))
            return RPCResponse(
                ok=checkpoint is not None,
                result={
                    "checkpoint": checkpoint,
                    "current_finality_round": self.current_finality_round,
                    "current_finality_checkpoint_id": self.current_finality_checkpoint_id,
                } if checkpoint is not None else {},
                error=None if checkpoint is not None else "round-unavailable",
            )
        if request.method == "finality_timeout_tick":
            return RPCResponse(ok=True, result=self.timeout_tick())
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
        if request.method == "get_finalized_batch":
            return RPCResponse(ok=True, result=self.export_finalized_l1_feed())
        if request.method == "get_l1_handoff":
            prefer_finalized = request.params.get("prefer_finalized", True)
            return RPCResponse(ok=True, result=self.export_l1_handoff(prefer_finalized=prefer_finalized))
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
        finality_result = self.reconcile_finality_with_peer(rpc_handler)
        response = rpc_handler(RPCRequest(method="get_sync_summary"))
        if not response.ok:
            return []
        missing = self.sync_frontier_from_peer(response.result)
        imported: List[str] = list(finality_result.get("imported_finalized_blocks", []))
        for block_hash in missing:
            fetched = self.fetch_missing_block_via_rpc(rpc_handler, block_hash)
            if fetched is not None and fetched not in imported:
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
            checkpoint_id = envelope.payload.get("finality", {}).get("latest_finalized_checkpoint")
            if checkpoint_id and checkpoint_id not in self.verified_finality_evidence:
                self.request_finality_evidence(envelope.origin, checkpoint_id)
            else:
                missing = self.sync_frontier_from_peer(envelope.payload)
                if missing:
                    self.request_missing_blocks(envelope.origin, missing)
        if envelope.kind == "finality-summary":
            checkpoint_id = envelope.payload.get("latest_finalized_checkpoint")
            if checkpoint_id and checkpoint_id not in self.verified_finality_evidence:
                self.request_finality_evidence(envelope.origin, checkpoint_id)
        if envelope.kind == "finality-vote":
            checkpoint = envelope.payload.get("checkpoint")
            vote = envelope.payload.get("vote")
            if checkpoint and vote and self._record_finality_vote(checkpoint, vote):
                if envelope.ttl > 1:
                    self.outbox.append(self._normalize_envelope(envelope.forward(self.node_id)))
        if envelope.kind == "finality-request":
            checkpoint_id = envelope.payload.get("checkpoint_id")
            if checkpoint_id:
                self.send_finality_evidence_to_peer(envelope.origin, checkpoint_id)
        if envelope.kind == "finality-certificate":
            checkpoint = envelope.payload.get("checkpoint")
            certificate = envelope.payload.get("certificate")
            if checkpoint and certificate:
                verified = self.verify_and_store_live_finality_certificate(checkpoint, certificate)
                if verified:
                    finalized_missing = self.finalized_blocks_missing_locally(
                        list(envelope.payload.get("finalized_block_hashes", []))
                    )
                    if finalized_missing:
                        self.request_missing_blocks(envelope.origin, finalized_missing)
                if verified and envelope.ttl > 1:
                    self.outbox.append(self._normalize_envelope(envelope.forward(self.node_id)))
        if envelope.kind == "finality-evidence":
            checkpoint = envelope.payload.get("checkpoint")
            certificate = envelope.payload.get("certificate")
            if checkpoint and certificate:
                verified = self.verify_and_store_finality_evidence(checkpoint, certificate)
                if verified:
                    finalized_missing = self.finalized_blocks_missing_locally(
                        list(envelope.payload.get("finalized_block_hashes", []))
                    )
                    if finalized_missing:
                        self.request_missing_blocks(envelope.origin, finalized_missing)
                    else:
                        frontier_missing = [
                            block_hash
                            for block_hash in envelope.payload.get("frontier", [])
                            if block_hash not in self.chain.block_by_hash
                        ]
                        if frontier_missing:
                            self.request_missing_blocks(envelope.origin, frontier_missing)
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

    def _checkpoint_dict(self, checkpoint_id: str | None = None) -> dict | None:
        checkpoints = self.chain.export_finality_state()["checkpoints"]
        if checkpoint_id is None:
            self._ensure_current_finality_round()
            if self.current_finality_checkpoint_id is not None:
                return next((item for item in checkpoints if item["checkpoint_id"] == self.current_finality_checkpoint_id), None)
            return checkpoints[-1] if checkpoints else None
        return next((item for item in checkpoints if item["checkpoint_id"] == checkpoint_id), None)

    def _record_finality_vote(self, checkpoint: dict, vote: dict) -> bool:
        if not self.chain.verify_finality_vote(checkpoint, vote):
            return False
        conflict = self._vote_conflict(checkpoint, vote)
        if conflict is not None:
            return False
        checkpoint_id = checkpoint["checkpoint_id"]
        votes = self.finality_votes.setdefault(checkpoint_id, {})
        voter_id = vote["voter_id"]
        if voter_id in votes:
            return False
        votes[voter_id] = dict(vote)
        self._maybe_finalize_from_votes(checkpoint)
        return True

    def _maybe_finalize_from_votes(self, checkpoint: dict) -> None:
        checkpoint_id = checkpoint["checkpoint_id"]
        votes = self.finality_votes.get(checkpoint_id, {})
        if not votes:
            return
        weight_map = self.chain.finality_weight_map()
        signer_set = sorted(voter_id for voter_id in votes if voter_id in weight_map)
        quorum_weight = sum(weight_map[voter_id] for voter_id in signer_set)
        if quorum_weight < self.chain.finality_quorum_threshold():
            return
        if checkpoint_id not in self.finality_certificates:
            lock_certificate = self.chain._certificate_to_dict(
                self.chain._build_finality_certificate(
                    epoch=checkpoint["epoch"],
                    round_index=checkpoint["round"],
                    vote_type="lock",
                    checkpoint_id=checkpoint_id,
                    committee_digest=checkpoint["committee_digest"],
                    quorum_weight=quorum_weight,
                    signers=signer_set,
                )
            )
            self.finality_certificates[checkpoint_id] = {
                "checkpoint": dict(checkpoint),
                "certificate": lock_certificate,
            }
            self.advance_finality_round(force=False)
        if checkpoint["round"] <= 1:
            return
        previous_checkpoint = self._checkpoint_dict_by_round(checkpoint["round"] - 1)
        if previous_checkpoint is None:
            return
        previous_id = previous_checkpoint["checkpoint_id"]
        if previous_id in self.verified_finality_evidence:
            return
        finalize_certificate = self.chain._certificate_to_dict(
            self.chain._build_finality_certificate(
                epoch=checkpoint["epoch"],
                round_index=checkpoint["round"],
                vote_type="finalize",
                checkpoint_id=previous_id,
                committee_digest=checkpoint["committee_digest"],
                quorum_weight=quorum_weight,
                signers=signer_set,
            )
        )
        if not self.verify_and_store_live_finality_certificate(previous_checkpoint, finalize_certificate):
            return
        finalized_block_hashes = self.chain.confirmed_order()[: previous_checkpoint["ordered_prefix_end"] + 1]
        self.outbox.append(
            self._normalize_envelope(
                GossipEnvelope(
                    kind="finality-certificate",
                    origin=self.node_id,
                    payload={
                        "checkpoint": previous_checkpoint,
                        "certificate": finalize_certificate,
                        "finalized_block_hashes": finalized_block_hashes,
                        "frontier": list(self.chain.frontier),
                    },
                )
            )
        )
        self.advance_finality_round(force=False)

    def _checkpoint_dict_by_round(self, round_index: int) -> dict | None:
        return next(
            (item for item in self.chain.export_finality_state()["checkpoints"] if item["round"] == round_index),
            None,
        )

    def _ensure_current_finality_round(self) -> None:
        checkpoints = self.chain.export_finality_state()["checkpoints"]
        if not checkpoints:
            self.current_finality_round = 0
            self.current_finality_checkpoint_id = None
            return
        checkpoint_by_round = {item["round"]: item for item in checkpoints}
        latest_round = checkpoints[-1]["round"]
        if self.current_finality_round <= 0:
            self.current_finality_round = 1
        if self.current_finality_round > latest_round:
            self.current_finality_round = latest_round
        checkpoint = checkpoint_by_round.get(self.current_finality_round)
        if checkpoint is None:
            checkpoint = checkpoints[-1]
            self.current_finality_round = checkpoint["round"]
        self.current_finality_checkpoint_id = checkpoint["checkpoint_id"]

    def _vote_conflict(self, checkpoint: dict, vote: dict) -> dict | None:
        voter_id = vote["voter_id"]
        round_index = vote["round"]
        checkpoint_id = vote["checkpoint_id"]
        for existing_checkpoint_id, votes in self.finality_votes.items():
            existing_vote = votes.get(voter_id)
            if existing_vote is None:
                continue
            if existing_vote["round"] != round_index:
                continue
            if existing_checkpoint_id == checkpoint_id:
                continue
            return self._record_finality_conflict(
                {
                    "type": "conflicting-vote",
                    "voter_id": voter_id,
                    "round": round_index,
                    "checkpoint_id": checkpoint_id,
                    "conflicting_checkpoint_id": existing_checkpoint_id,
                    "vote_type": vote["vote_type"],
                }
            )
        return None

    def _certificate_conflict(self, checkpoint: dict, certificate: dict) -> dict | None:
        checkpoint_id = checkpoint["checkpoint_id"]
        vote_type = certificate["vote_type"]
        round_index = certificate["round"]
        existing_for_checkpoint = self.finality_certificates.get(checkpoint_id)
        if existing_for_checkpoint is not None:
            existing_certificate = existing_for_checkpoint["certificate"]
            if existing_certificate.get("certificate_digest") != certificate.get("certificate_digest"):
                return self._record_finality_conflict(
                    {
                        "type": "conflicting-certificate",
                        "round": round_index,
                        "vote_type": vote_type,
                        "checkpoint_id": checkpoint_id,
                        "conflicting_checkpoint_id": checkpoint_id,
                        "existing_certificate_digest": existing_certificate.get("certificate_digest"),
                        "new_certificate_digest": certificate.get("certificate_digest"),
                    }
                )
        for existing_checkpoint_id, entry in self.finality_certificates.items():
            existing_certificate = entry["certificate"]
            if existing_certificate.get("round") != round_index:
                continue
            if existing_certificate.get("vote_type") != vote_type:
                continue
            if existing_checkpoint_id == checkpoint_id:
                continue
            return self._record_finality_conflict(
                {
                    "type": "conflicting-certificate",
                    "round": round_index,
                    "vote_type": vote_type,
                    "checkpoint_id": checkpoint_id,
                    "conflicting_checkpoint_id": existing_checkpoint_id,
                    "existing_certificate_digest": existing_certificate.get("certificate_digest"),
                    "new_certificate_digest": certificate.get("certificate_digest"),
                }
            )
        return None

    def _record_finality_conflict(self, conflict: dict) -> dict:
        if conflict not in self.finality_conflicts:
            self.finality_conflicts.append(dict(conflict))
        return conflict
