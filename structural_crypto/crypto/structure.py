"""Structure-function utilities used by policy-bound signatures."""

from __future__ import annotations

import hashlib
import hmac
import math
from dataclasses import dataclass
from typing import List


STRUCTURE_DOMAIN = 2**24
CHALLENGE_POINTS = (101, 211, 307)


@dataclass(frozen=True)
class StructureParameters:
    amplitudes: List[float]
    frequencies: List[float]
    phases: List[float]
    tau: float
    sigma: float


def _float_from_bytes(data: bytes) -> float:
    return int.from_bytes(data, "big") / 2**32


def derive_parameters(seed: bytes) -> StructureParameters:
    key = b"structkey"
    raw = b"".join(
        hmac.new(key, seed + bytes([index]), hashlib.sha256).digest()
        for index in range(3)
    )
    values = [_float_from_bytes(raw[i : i + 4]) for i in range(0, 48, 4)]
    amplitudes = [1.0 + (values[i] * 2.0) for i in range(3)]
    frequencies = [0.5 + (values[i] * 20.0) for i in range(3, 6)]
    phases = [values[i] * (2 * math.pi) for i in range(6, 9)]
    samples = [phi(x, amplitudes, frequencies, phases) for x in CHALLENGE_POINTS]
    tau = sorted(samples)[1]
    sigma = math.sqrt(sum((sample - tau) ** 2 for sample in samples) / len(samples))
    return StructureParameters(amplitudes, frequencies, phases, tau, sigma)


def phi(x: int, amplitudes: List[float], frequencies: List[float], phases: List[float]) -> float:
    return sum(
        amplitudes[i] * math.cos(frequencies[i] * math.log(x + 1) + phases[i])
        for i in range(3)
    )


def structure_hash(message: bytes) -> int:
    return int.from_bytes(hashlib.sha256(message).digest(), "big") % STRUCTURE_DOMAIN


def evaluate_delta(message: str, params: StructureParameters) -> tuple[int, float, float]:
    x_value = structure_hash(message.encode("utf-8"))
    phi_value = phi(
        x_value,
        params.amplitudes,
        params.frequencies,
        params.phases,
    )
    delta = abs(phi_value - params.tau)
    return x_value, phi_value, delta

