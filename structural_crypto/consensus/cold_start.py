"""Cold-start model for Proof of Compliant Trajectory (PoCT)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable


@dataclass(frozen=True)
class BootstrapCredential:
    """External evidence used to improve an identity's starting tier."""

    source: str
    score: float


@dataclass(frozen=True)
class ColdStartConfig:
    """Parameters for PoCT identity maturation."""

    probation_txs: int = 5
    mature_txs: int = 20
    min_score_for_ordering: float = 0.15
    base_reward_share: float = 0.05
    max_reward_share: float = 1.0
    external_boost_cap: float = 0.25
    compliant_delta_weight: float = 0.5
    history_weight: float = 0.35
    stability_weight: float = 0.15


@dataclass
class ColdStartState:
    """Track an identity's early lifecycle under PoCT."""

    identity: str
    compliant_txs: int = 0
    rejected_txs: int = 0
    average_delta: float = 0.0
    branch_conflicts: int = 0
    external_credential_score: float = 0.0
    phase: str = field(default="new")

    def total_txs(self) -> int:
        return self.compliant_txs + self.rejected_txs


class ColdStartEngine:
    """Compute ordering and reward eligibility from trajectory growth."""

    def __init__(self, config: ColdStartConfig | None = None):
        self.config = config or ColdStartConfig()

    def register_identity(
        self,
        identity: str,
        credentials: Iterable[BootstrapCredential] = (),
    ) -> ColdStartState:
        external_score = sum(max(0.0, credential.score) for credential in credentials)
        external_score = min(external_score, self.config.external_boost_cap)
        state = ColdStartState(
            identity=identity,
            external_credential_score=external_score,
        )
        state.phase = self.phase_for(state)
        return state

    def record_compliant_tx(self, state: ColdStartState, delta: float) -> ColdStartState:
        total = state.compliant_txs + 1
        averaged = ((state.average_delta * state.compliant_txs) + delta) / total
        state.compliant_txs = total
        state.average_delta = averaged
        state.phase = self.phase_for(state)
        return state

    def record_rejected_tx(self, state: ColdStartState, branch_conflict: bool = False) -> ColdStartState:
        state.rejected_txs += 1
        if branch_conflict:
            state.branch_conflicts += 1
        state.phase = self.phase_for(state)
        return state

    def phase_for(self, state: ColdStartState) -> str:
        if state.compliant_txs >= self.config.mature_txs and state.branch_conflicts == 0:
            return "mature"
        if state.compliant_txs >= self.config.probation_txs:
            return "probation"
        return "new"

    def ordering_score(self, state: ColdStartState) -> float:
        history_component = min(state.compliant_txs / self.config.mature_txs, 1.0)
        if state.compliant_txs == 0:
            delta_component = 0.0
        else:
            delta_component = max(0.0, 1.0 - min(state.average_delta / 3.0, 1.0))
        total_txs = max(1, state.total_txs())
        stability_component = max(
            0.0,
            1.0 - ((state.rejected_txs + state.branch_conflicts) / total_txs),
        )
        score = (
            history_component * self.config.history_weight
            + delta_component * self.config.compliant_delta_weight
            + stability_component * self.config.stability_weight
            + state.external_credential_score
        )
        return min(max(score, 0.0), 1.0)

    def can_participate_in_ordering(self, state: ColdStartState) -> bool:
        if state.compliant_txs < self.config.probation_txs:
            return False
        return self.ordering_score(state) >= self.config.min_score_for_ordering

    def reward_share(self, state: ColdStartState) -> float:
        score = self.ordering_score(state)
        return min(
            self.config.max_reward_share,
            self.config.base_reward_share + score * (self.config.max_reward_share - self.config.base_reward_share),
        )
