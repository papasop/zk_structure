"""Hot identity state store and snapshot-friendly helpers."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Dict, Iterable

from .models import IdentityState


class IdentityStateStore:
    """Keep finalized hot identity states in a compact in-memory map."""

    def __init__(self, states: Iterable[IdentityState] = ()) -> None:
        self._states: Dict[str, IdentityState] = {state.identity_id: state for state in states}

    def get(self, identity_id: str) -> IdentityState | None:
        return self._states.get(identity_id)

    def require(self, identity_id: str) -> IdentityState:
        state = self.get(identity_id)
        if state is None:
            raise KeyError(f"unknown identity: {identity_id}")
        return state

    def put(self, state: IdentityState) -> IdentityState:
        self._states[state.identity_id] = state
        return state

    def values(self) -> list[IdentityState]:
        return [self._states[identity_id] for identity_id in sorted(self._states)]

    def export_state(self) -> dict:
        return {
            "identity_count": len(self._states),
            "states": [asdict(state) for state in self.values()],
        }

    def state_root(self) -> str:
        payload = json.dumps(self.export_state(), sort_keys=True, separators=(",", ":")).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()
