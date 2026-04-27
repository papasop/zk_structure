"""Wallet utilities for the demo chain."""

from __future__ import annotations

from dataclasses import dataclass

from structural_crypto.crypto.signature import StructurePrivateKey


@dataclass
class Wallet:
    name: str
    seed: str

    @property
    def key(self) -> StructurePrivateKey:
        return StructurePrivateKey(owner=self.name, seed=self.seed)

    @property
    def address(self) -> str:
        return self.key.public_key

