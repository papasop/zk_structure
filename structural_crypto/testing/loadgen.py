"""Simple agent and load generation helpers for benchmark scaffolding."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.ledger import Blockchain, Transaction
from structural_crypto.node import Wallet


@dataclass(frozen=True)
class AgentSpec:
    wallet: Wallet
    recipients: List[str]
    amount: int = 1
    epsilon: float = 10.0


class LoadGenerator:
    def __init__(self, chain: Blockchain):
        self.chain = chain

    def build_transactions(self, agents: List[AgentSpec], timestamp: int) -> List[Transaction]:
        built: List[Transaction] = []
        for agent in agents:
            policy = PolicyCommitment.from_values(
                epsilon=agent.epsilon,
                max_amount=agent.amount,
                allowed_recipients=list(agent.recipients),
            )
            tx = self.chain.build_transaction(
                key=agent.wallet.key,
                recipients=[(agent.recipients[0], agent.amount)],
                policy=policy,
                timestamp=timestamp,
            )
            built.append(tx)
        return built
