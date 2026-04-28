"""Shared ledger datatypes."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.crypto.signature import StructureSignature


@dataclass(frozen=True)
class TxInput:
    prev_txid: str
    output_index: int
    owner: str


@dataclass(frozen=True)
class TxOutput:
    amount: int
    recipient: str


@dataclass(frozen=True)
class Transaction:
    txid: str
    sender: str
    trajectory_id: Optional[str]
    prev: Optional[str]
    sequence: int
    epoch: int
    policy_hash: str
    delta: float
    sender_head_commitment: str
    inputs: List[TxInput]
    outputs: List[TxOutput]
    message: str
    policy: PolicyCommitment
    signature: StructureSignature
    timestamp: int
    identity_id: Optional[str] = None
    action_type: str = "transfer"
    action_key: Optional[str] = None
    approvals: List[Dict[str, Any]] = field(default_factory=list)
    action_payload: Dict[str, Any] = field(default_factory=dict)
    recovery_policy_version: Optional[int] = None
    pending_recovery_id: Optional[str] = None

    def total_output(self) -> int:
        return sum(output.amount for output in self.outputs)

    def recipients(self) -> List[str]:
        return [output.recipient for output in self.outputs]

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        data["policy"]["allowed_recipients"] = list(self.policy.allowed_recipients)
        return data


@dataclass
class SenderTrajectoryState:
    sender: str
    trajectory_id: Optional[str] = None
    head_txid: Optional[str] = None
    sequence: int = -1
    recent_epochs: List[int] = field(default_factory=list)
    phase: str = "new"
    branch_conflicts: int = 0


@dataclass(frozen=True)
class Block:
    index: int
    parents: List[str]
    timestamp: int
    nonce: int
    difficulty: int
    producer_id: str
    producer_phase: str
    producer_ordering_score: float
    producer_weight_snapshot: float
    dynamic_k_snapshot: float
    aggregate_delta: float
    trajectory_commitment: str
    virtual_order_hint: str
    transactions: List[Transaction]
    merkle_root: str
    block_hash: str

    @property
    def prev_hash(self) -> str:
        return self.parents[0] if self.parents else "0" * 64


@dataclass(frozen=True)
class FinalityCommitteeMember:
    identity_id: str
    phase: str
    ordering_score: float
    finality_weight: float
    committee_epoch: int


@dataclass(frozen=True)
class FinalityCertificate:
    epoch: int
    round: int
    vote_type: str
    checkpoint_id: str
    quorum_weight: float
    committee_digest: str
    signer_set: List[str]
    certificate_digest: str


@dataclass(frozen=True)
class FinalityVote:
    epoch: int
    round: int
    vote_type: str
    checkpoint_id: str
    committee_digest: str
    voter_id: str
    voter_weight: float
    vote_digest: str


@dataclass(frozen=True)
class FinalityCheckpoint:
    checkpoint_id: str
    epoch: int
    round: int
    anchor_block_hash: str
    finalized_parent: Optional[str]
    ordered_prefix_end: int
    ordered_prefix_digest: str
    confirmed_batch_digest: str
    committee_digest: str
    config_digest: str
    lock_certificate: Optional[FinalityCertificate] = None
    finalize_certificate: Optional[FinalityCertificate] = None
