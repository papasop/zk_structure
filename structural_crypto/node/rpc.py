"""Minimal RPC request and response helpers for headless nodes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass(frozen=True)
class RPCRequest:
    method: str
    params: Dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RPCResponse:
    ok: bool
    result: Dict[str, Any] = field(default_factory=dict)
    error: str | None = None
