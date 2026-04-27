"""Small end-to-end demo for the minimal blockchain."""

from __future__ import annotations

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.ledger.blockchain import Blockchain
from structural_crypto.node.wallet import Wallet


def run_demo() -> dict:
    chain = Blockchain(difficulty=2, mining_reward=10)
    alice = Wallet(name="alice", seed="alice-seed")
    bob = Wallet(name="bob", seed="bob-seed")
    miner = Wallet(name="miner", seed="miner-seed")

    chain.faucet(alice.address, 100)

    policy = PolicyCommitment.from_values(
        epsilon=10.0,
        max_amount=30,
        allowed_recipients=[bob.address],
    )
    tx = chain.build_transaction(
        key=alice.key,
        recipients=[(bob.address, 25)],
        policy=policy,
    )
    chain.add_transaction(tx, signer_seed=alice.seed)
    block = chain.mine_block(miner.address)

    return {
        "block_index": block.index,
        "block_hash": block.block_hash,
        "balances": chain.balances(),
        "trajectories": chain.trajectory_summary(),
        "valid": chain.validate_chain(),
        "summary": chain.chain_summary(),
    }
