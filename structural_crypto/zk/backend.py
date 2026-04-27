"""Minimal zk backend interfaces for prototype integration tests."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Dict, Protocol


@dataclass(frozen=True)
class ZKProof:
    backend: str
    circuit_id: str
    public_inputs: Dict[str, Any]
    proof_blob: str


class ZKBackend(Protocol):
    backend_name: str

    def prove(self, circuit_id: str, witness: Dict[str, Any], public_inputs: Dict[str, Any]) -> ZKProof:
        ...

    def verify(self, proof: ZKProof) -> bool:
        ...


class MockZKBackend:
    """Deterministic placeholder backend until a real prover is wired in."""

    backend_name = "mock-zk"

    def prove(self, circuit_id: str, witness: Dict[str, Any], public_inputs: Dict[str, Any]) -> ZKProof:
        payload = {
            "circuit_id": circuit_id,
            "witness": witness,
            "public_inputs": public_inputs,
        }
        proof_blob = hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return ZKProof(
            backend=self.backend_name,
            circuit_id=circuit_id,
            public_inputs=dict(public_inputs),
            proof_blob=proof_blob,
        )

    def verify(self, proof: ZKProof) -> bool:
        return proof.backend == self.backend_name and len(proof.proof_blob) == 64
