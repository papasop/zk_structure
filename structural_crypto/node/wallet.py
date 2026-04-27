"""Wallet utilities for the demo chain."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

from structural_crypto.crypto.signature import StructurePrivateKey

MNEMONIC_WORDS = [
    "able", "about", "absorb", "access", "across", "action", "adapt", "admit",
    "agent", "agree", "alert", "alpha", "anchor", "ancient", "angle", "apple",
    "arena", "artist", "aspect", "atom", "autumn", "balance", "bamboo", "basic",
    "beacon", "before", "begin", "belief", "below", "bird", "blade", "bless",
    "bloom", "blue", "border", "brave", "breeze", "bridge", "bright", "brother",
    "cabin", "calm", "camera", "candle", "canvas", "captain", "carbon", "carry",
    "castle", "casual", "center", "chance", "change", "chapter", "circle", "citizen",
    "clarity", "classic", "cloud", "coast", "cobalt", "comfort", "common", "copper",
    "corner", "cradle", "craft", "crystal", "cycle", "dance", "dawn", "decent",
    "deep", "delta", "desert", "detail", "diamond", "distant", "doctor", "dream",
    "drift", "earth", "echo", "ember", "energy", "engine", "equal", "essence",
    "evening", "ever", "exact", "exile", "fabric", "falcon", "family", "fancy",
    "field", "filter", "final", "flame", "flower", "focus", "forest", "fortune",
    "frame", "future", "galaxy", "garden", "gentle", "globe", "glory", "golden",
    "grace", "grain", "gravity", "green", "guide", "harbor", "harmony", "hazel",
    "hero", "hidden", "honor", "horizon", "humble", "ice", "idea", "impact",
    "indigo", "island", "jewel", "journey", "joy", "juniper", "kernel", "kingdom",
    "ladder", "lake", "lantern", "legend", "lemon", "level", "liberty", "light",
    "linen", "lively", "logic", "lotus", "lunar", "magic", "maple", "marble",
    "meadow", "melody", "memory", "merit", "midnight", "mirror", "modern", "moment",
    "mountain", "music", "native", "nature", "navy", "noble", "north", "novel",
    "oasis", "ocean", "olive", "omega", "orbit", "origin", "panel", "paper",
    "parent", "path", "pearl", "pepper", "phoenix", "piano", "planet", "plaza",
    "poem", "polar", "prairie", "prime", "prism", "public", "pulse", "quality",
    "quantum", "quiet", "radar", "rain", "random", "rapid", "reason", "record",
    "reef", "relief", "ribbon", "river", "rocket", "royal", "sacred", "saddle",
    "sail", "sample", "scale", "science", "season", "shadow", "signal", "silver",
    "simple", "skill", "smile", "solar", "solid", "spirit", "spring", "stable",
    "star", "stone", "story", "sunset", "swift", "talent", "temple", "theory",
    "thrive", "timber", "titan", "today", "token", "torch", "travel", "trust",
    "unity", "urban", "valid", "valley", "velvet", "victory", "violet", "vision",
    "vital", "voyage", "warm", "water", "whisper", "window", "wisdom", "wonder",
    "world", "yonder", "young", "zephyr",
]


@dataclass(init=False)
class Wallet:
    name: str
    mnemonic: str

    def __init__(self, name: str, mnemonic: str | None = None, seed: str | None = None):
        self.name = name
        self.mnemonic = mnemonic or seed or self.generate_mnemonic()

    @property
    def key(self) -> StructurePrivateKey:
        return StructurePrivateKey(owner=self.name, seed=self.mnemonic)

    @property
    def address(self) -> str:
        return self.key.public_key

    @property
    def seed(self) -> str:
        """Backward-compatible alias for older code paths."""
        return self.mnemonic

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "mnemonic": self.mnemonic,
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
        mnemonic = data.get("mnemonic") or data.get("seed")
        if not mnemonic:
            raise ValueError("wallet file is missing mnemonic")
        return cls(name=data["name"], mnemonic=mnemonic)

    @classmethod
    def create(cls, name: str, seed: str | None = None, mnemonic: str | None = None) -> "Wallet":
        phrase = mnemonic or seed or cls.generate_mnemonic()
        return cls(name=name, mnemonic=phrase)

    @staticmethod
    def default_path(name: str, base_dir: str | Path = ".poct/wallets") -> Path:
        return Path(base_dir) / f"{name}.json"

    @staticmethod
    def generate_mnemonic(words: int = 12) -> str:
        return " ".join(secrets.choice(MNEMONIC_WORDS) for _ in range(words))
