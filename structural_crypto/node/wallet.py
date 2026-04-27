"""Wallet utilities for the demo chain."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

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

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "seed": self.seed,
            "address": self.address,
        }

    def save(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True), encoding="utf-8")
        return target

    @classmethod
    def load(cls, path: str | Path) -> "Wallet":
        source = Path(path)
        data = json.loads(source.read_text(encoding="utf-8"))
        return cls(name=data["name"], seed=data["seed"])

    @classmethod
    def create(cls, name: str, seed: str | None = None) -> "Wallet":
        return cls(name=name, seed=seed or secrets.token_hex(16))

    @staticmethod
    def default_path(name: str, base_dir: str | Path = ".poct/wallets") -> Path:
        return Path(base_dir) / f"{name}.json"
