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
    prev_hash: str
    timestamp: int
    nonce: int
    difficulty: int
    transactions: List[Transaction]
    merkle_root: str
    block_hash: str
