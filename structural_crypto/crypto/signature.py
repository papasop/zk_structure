"""Simplified structure-bound signatures for the demo chain."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .policy import PolicyCommitment
from .structure import StructureParameters, derive_parameters, evaluate_delta


@dataclass(frozen=True)
class StructureSignature:
    signer: str
    signature_hex: str
    x_value: int
    phi_value: float
    delta: float
    tau: float
    sigma: float


class StructurePrivateKey:
    """A deterministic private key that signs policy-bound messages."""

    def __init__(self, owner: str, seed: str):
        self.owner = owner
        self.seed = seed
        self._seed_bytes = seed.encode("utf-8")
        self._params = derive_parameters(self._seed_bytes)
        self.public_key = hashlib.sha256(self._seed_bytes).hexdigest()

    @property
    def params(self) -> StructureParameters:
        return self._params

    def sign(self, message: str, policy: PolicyCommitment, amount: int, recipients: list[str]) -> StructureSignature:
        x_value, phi_value, delta = evaluate_delta(message, self._params)
        policy.validate(delta=delta, amount=amount, recipients=recipients)
        payload = (
            f"{self.public_key}|{message}|{x_value}|{phi_value:.12f}|"
            f"{delta:.12f}|{self._params.tau:.12f}|{policy.epsilon:.12f}"
        ).encode("utf-8")
        signature_hex = hashlib.sha256(payload).hexdigest()
        return StructureSignature(
            signer=self.public_key,
            signature_hex=signature_hex,
            x_value=x_value,
            phi_value=phi_value,
            delta=delta,
            tau=self._params.tau,
            sigma=self._params.sigma,
        )

    @staticmethod
    def verify(
        message: str,
        policy: PolicyCommitment,
        amount: int,
        recipients: list[str],
        public_key: str,
        seed: str,
        signature: StructureSignature,
    ) -> bool:
        private_key = StructurePrivateKey(owner="verifier", seed=seed)
        if private_key.public_key != public_key:
            return False
        x_value, phi_value, delta = evaluate_delta(message, private_key.params)
        try:
            policy.validate(delta=delta, amount=amount, recipients=recipients)
        except Exception:
            return False
        payload = (
            f"{public_key}|{message}|{x_value}|{phi_value:.12f}|"
            f"{delta:.12f}|{private_key.params.tau:.12f}|{policy.epsilon:.12f}"
        ).encode("utf-8")
        expected = hashlib.sha256(payload).hexdigest()
        return (
            signature.signature_hex == expected
            and signature.x_value == x_value
            and abs(signature.phi_value - phi_value) < 1e-12
            and abs(signature.delta - delta) < 1e-12
        )

