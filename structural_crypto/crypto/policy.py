"""Policy commitments for behavior-bound transactions."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional


class PolicyError(ValueError):
    """Raised when a transaction violates its policy commitment."""


@dataclass(frozen=True)
class PolicyCommitment:
    epsilon: float
    max_amount: Optional[int] = None
    allowed_recipients: tuple[str, ...] = field(default_factory=tuple)

    @classmethod
    def from_values(
        cls,
        epsilon: float,
        max_amount: Optional[int] = None,
        allowed_recipients: Optional[Iterable[str]] = None,
    ) -> "PolicyCommitment":
        recipients = tuple(sorted(allowed_recipients or ()))
        return cls(epsilon=epsilon, max_amount=max_amount, allowed_recipients=recipients)

    def validate(self, delta: float, amount: int, recipients: Iterable[str]) -> None:
        if delta >= self.epsilon:
            raise PolicyError(
                f"delta {delta:.6f} exceeds policy epsilon {self.epsilon:.6f}"
            )
        if self.max_amount is not None and amount > self.max_amount:
            raise PolicyError(
                f"amount {amount} exceeds policy max_amount {self.max_amount}"
            )
        allowed = set(self.allowed_recipients)
        if allowed:
            invalid = [recipient for recipient in recipients if recipient not in allowed]
            if invalid:
                raise PolicyError(
                    f"recipient(s) {', '.join(invalid)} are not allowed by policy"
                )

