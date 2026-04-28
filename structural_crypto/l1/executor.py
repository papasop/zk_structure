"""Minimal L1 batch consumer and checkpoint logic."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class L1Checkpoint:
    batch_digest: str
    batch_id: str
    state_root: str
    tx_count: int


class SimpleL1Executor:
    """Applies L0-exported batches into a toy replayable L1 state."""

    def __init__(self) -> None:
        self.accounts: Dict[str, int] = {}
        self.last_checkpoint: L1Checkpoint | None = None

    def apply_batch(self, batch: dict) -> L1Checkpoint:
        for tx in batch.get("transactions", []):
            sender = tx["sender"]
            if sender != "GENESIS":
                sent_amount = sum(output["amount"] for output in tx["outputs"] if output["recipient"] != sender)
                self.accounts[sender] = self.accounts.get(sender, 0) - sent_amount
            for output in tx["outputs"]:
                self.accounts[output["recipient"]] = self.accounts.get(output["recipient"], 0) + output["amount"]
        digest = self.batch_digest(batch)
        batch_id = hashlib.sha256(
            json.dumps(
                {"mode": batch.get("mode"), "digest": digest},
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        state_root = hashlib.sha256(
            json.dumps(self.accounts, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        checkpoint = L1Checkpoint(
            batch_digest=digest,
            batch_id=batch_id,
            state_root=state_root,
            tx_count=len(batch.get("transactions", [])),
        )
        self.last_checkpoint = checkpoint
        return checkpoint

    def apply_handoff(self, handoff: dict) -> L1Checkpoint:
        return self.apply_batch(handoff["batch"])

    @staticmethod
    def batch_digest(batch: dict) -> str:
        stable_view = {
            "mode": batch.get("mode"),
            "block_hashes": batch.get("block_hashes", []),
            "txids": [tx["txid"] for tx in batch.get("transactions", [])],
        }
        return hashlib.sha256(
            json.dumps(stable_view, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
