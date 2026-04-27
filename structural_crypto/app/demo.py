"""Small end-to-end demo for the minimal blockchain."""

from __future__ import annotations

from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.ledger.blockchain import Blockchain
from structural_crypto.node.wallet import Wallet


def build_demo_chain() -> Blockchain:
    chain = Blockchain(
        difficulty=2,
        producer_reward=10,
        allow_new_producers=True,
    )
    alice = Wallet(name="alice", seed="alice-seed")
    bob = Wallet(name="bob", seed="bob-seed")
    producer = Wallet(name="producer", seed="producer-seed")

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
    chain.produce_block(producer.address)
    return chain


def run_demo() -> dict:
    chain = build_demo_chain()
    block = chain.blocks[-1]
    return {
        "block_index": block.index,
        "block_hash": block.block_hash,
        "balances": chain.balances(),
        "accepted_virtual_transactions": chain.accepted_virtual_transactions(),
        "confirmed_order": chain.confirmed_order(),
        "confirmed_l1_batch": chain.confirmed_l1_batch(),
        "confirmed_rewards": chain.confirmed_reward_totals(),
        "export_l1_feed": chain.export_l1_feed(),
        "frontier": list(chain.frontier),
        "resolved_virtual_blocks": chain.resolved_virtual_blocks(),
        "trajectories": chain.trajectory_summary(),
        "valid": chain.validate_chain(),
        "virtual_order": chain.virtual_order(),
        "summary": chain.chain_summary(),
    }
