"""CLI for the minimal Structural Cryptography blockchain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_crypto.app.demo import build_demo_chain, run_demo
from structural_crypto.crypto.policy import PolicyCommitment
from structural_crypto.ledger.blockchain import Blockchain
from structural_crypto.node import Wallet


def _resolve_state_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg)
    return Blockchain.default_state_path()


def _resolve_wallet_path(path_arg: str | None, name: str | None = None) -> Path:
    if path_arg:
        return Path(path_arg)
    if not name:
        raise ValueError("wallet name is required when no wallet path is provided")
    return Wallet.default_path(name)


def _recipient_from_args(wallet_path: str | None, wallet_name: str | None, recipient: str | None) -> str:
    if recipient:
        return recipient
    target = _resolve_wallet_path(wallet_path, wallet_name)
    return Wallet.load(target).address


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="structural-chain",
        description="Minimal policy-enforced UTXO blockchain built from Structural Cryptography.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo", help="run the built-in blockchain demo")

    init_parser = subparsers.add_parser("init", help="create and persist an empty local chain state")
    init_parser.add_argument("--path", help="path to the state JSON file")
    init_parser.add_argument("--difficulty", type=int, default=1, help="block seal difficulty")
    init_parser.add_argument("--producer-reward", type=int, default=10, help="producer reward amount")
    init_parser.add_argument(
        "--allow-new-producers",
        action="store_true",
        help="allow new identities to produce blocks in this local chain",
    )

    save_parser = subparsers.add_parser("save", help="write a demo chain state file")
    save_parser.add_argument("--path", help="path to the state JSON file")

    persist_demo_parser = subparsers.add_parser(
        "persist-demo",
        help="build the demo chain and persist it to a state file",
    )
    persist_demo_parser.add_argument("--path", help="path to the state JSON file")

    load_parser = subparsers.add_parser("load", help="load and print a saved chain summary")
    load_parser.add_argument("--path", help="path to the state JSON file")

    frontier_parser = subparsers.add_parser("show-frontier", help="show DAG frontier from a saved state")
    frontier_parser.add_argument("--path", help="path to the state JSON file")

    confirmed_parser = subparsers.add_parser("show-confirmed", help="show confirmed virtual order from a saved state")
    confirmed_parser.add_argument("--path", help="path to the state JSON file")

    rewards_parser = subparsers.add_parser("show-rewards", help="show confirmed reward totals from a saved state")
    rewards_parser.add_argument("--path", help="path to the state JSON file")

    dag_parser = subparsers.add_parser("show-dag", help="show DAG block metadata from a saved state")
    dag_parser.add_argument("--path", help="path to the state JSON file")

    virtual_parser = subparsers.add_parser("show-virtual", help="show virtual DAG order from a saved state")
    virtual_parser.add_argument("--path", help="path to the state JSON file")

    resolved_parser = subparsers.add_parser(
        "show-resolved",
        help="show accepted and rejected transactions under virtual conflict resolution",
    )
    resolved_parser.add_argument("--path", help="path to the state JSON file")

    l1_parser = subparsers.add_parser(
        "show-l1-feed",
        help="show the exported L1 feed from a saved state",
    )
    l1_parser.add_argument("--path", help="path to the state JSON file")
    l1_parser.add_argument(
        "--mode",
        choices=["confirmed", "virtual"],
        default="confirmed",
        help="feed scope to export",
    )

    wallet_create_parser = subparsers.add_parser("wallet-create", help="create a local CLI wallet file")
    wallet_create_parser.add_argument("--name", required=True, help="wallet name")
    wallet_create_parser.add_argument("--seed", help="optional deterministic seed")
    wallet_create_parser.add_argument("--mnemonic", help="optional mnemonic phrase")
    wallet_create_parser.add_argument("--path", help="wallet JSON path")

    wallet_show_parser = subparsers.add_parser("wallet-show", help="show a local CLI wallet file")
    wallet_show_parser.add_argument("--path", help="wallet JSON path")
    wallet_show_parser.add_argument("--name", help="wallet name if using default path")

    wallet_address_parser = subparsers.add_parser("wallet-address", help="show only the wallet address")
    wallet_address_parser.add_argument("--path", help="wallet JSON path")
    wallet_address_parser.add_argument("--name", help="wallet name if using default wallet path")

    faucet_parser = subparsers.add_parser("faucet", help="mint funds into a wallet or address on a saved local chain")
    faucet_parser.add_argument("--path", help="path to the state JSON file")
    faucet_parser.add_argument("--recipient", help="explicit recipient address")
    faucet_parser.add_argument("--wallet-path", help="recipient wallet JSON path")
    faucet_parser.add_argument("--wallet-name", help="recipient wallet name if using default wallet path")
    faucet_parser.add_argument("--amount", required=True, type=int, help="amount to mint")

    send_parser = subparsers.add_parser("send", help="build and submit a transaction into a saved local chain")
    send_parser.add_argument("--path", help="path to the state JSON file")
    send_parser.add_argument("--wallet-path", help="sender wallet JSON path")
    send_parser.add_argument("--wallet-name", help="sender wallet name if using default wallet path")
    send_parser.add_argument("--to", required=True, help="recipient address")
    send_parser.add_argument("--amount", required=True, type=int, help="transfer amount")
    send_parser.add_argument("--epsilon", type=float, default=10.0, help="policy epsilon")
    send_parser.add_argument("--max-amount", type=int, help="policy max amount; defaults to transfer amount")

    produce_parser = subparsers.add_parser("produce", help="produce a block on a saved local chain")
    produce_parser.add_argument("--path", help="path to the state JSON file")
    produce_parser.add_argument("--wallet-path", help="producer wallet JSON path")
    produce_parser.add_argument("--wallet-name", help="producer wallet name if using default wallet path")

    balance_parser = subparsers.add_parser("balance", help="show balance for a wallet or address on a saved local chain")
    balance_parser.add_argument("--path", help="path to the state JSON file")
    balance_parser.add_argument("--address", help="explicit address to query")
    balance_parser.add_argument("--wallet-path", help="wallet JSON path")
    balance_parser.add_argument("--wallet-name", help="wallet name if using default wallet path")

    args = parser.parse_args()
    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, sort_keys=True))
        return

    if args.command == "init":
        chain = Blockchain(
            difficulty=args.difficulty,
            producer_reward=args.producer_reward,
            allow_new_producers=args.allow_new_producers,
        )
        target = _resolve_state_path(args.path)
        chain.save_state(target)
        print(
            json.dumps(
                {
                    "saved_to": str(target),
                    "frontier": list(chain.frontier),
                    "config": chain.export_state()["config"],
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "wallet-create":
        wallet = Wallet.create(name=args.name, seed=args.seed, mnemonic=args.mnemonic)
        target = _resolve_wallet_path(args.path, args.name)
        wallet.save(target)
        print(json.dumps({"wallet": wallet.to_dict(), "saved_to": str(target)}, indent=2, sort_keys=True))
        return

    if args.command == "wallet-show":
        target = _resolve_wallet_path(args.path, args.name)
        wallet = Wallet.load(target)
        print(json.dumps({"wallet": wallet.to_dict(), "path": str(target)}, indent=2, sort_keys=True))
        return

    if args.command == "wallet-address":
        target = _resolve_wallet_path(args.path, args.name)
        wallet = Wallet.load(target)
        print(json.dumps({"address": wallet.address, "name": wallet.name, "path": str(target)}, indent=2, sort_keys=True))
        return

    if args.command == "save":
        chain = build_demo_chain()
        target = _resolve_state_path(args.path)
        chain.save_state(target)
        print(json.dumps({"saved_to": str(target)}, indent=2, sort_keys=True))
        return

    if args.command == "persist-demo":
        chain = build_demo_chain()
        target = _resolve_state_path(args.path)
        chain.save_state(target)
        print(
            json.dumps(
                {
                    "saved_to": str(target),
                    "frontier": list(chain.frontier),
                    "virtual_order": chain.virtual_order(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    path = _resolve_state_path(getattr(args, "path", None))
    chain = Blockchain.load_state(path)

    if args.command == "faucet":
        recipient = _recipient_from_args(args.wallet_path, args.wallet_name, args.recipient)
        tx = chain.faucet(recipient, args.amount)
        chain.save_state(path)
        print(
            json.dumps(
                {
                    "txid": tx.txid,
                    "recipient": recipient,
                    "amount": args.amount,
                    "saved_to": str(path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "send":
        wallet = Wallet.load(_resolve_wallet_path(args.wallet_path, args.wallet_name))
        policy = PolicyCommitment.from_values(
            epsilon=args.epsilon,
            max_amount=args.max_amount if args.max_amount is not None else args.amount,
            allowed_recipients=[args.to],
        )
        tx = chain.build_transaction(
            key=wallet.key,
            recipients=[(args.to, args.amount)],
            policy=policy,
        )
        chain.add_transaction(tx, signer_seed=wallet.seed)
        chain.save_state(path)
        print(
            json.dumps(
                {
                    "txid": tx.txid,
                    "sender": wallet.address,
                    "recipient": args.to,
                    "amount": args.amount,
                    "saved_to": str(path),
                    "mempool_size": len(chain.mempool),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "produce":
        wallet = Wallet.load(_resolve_wallet_path(args.wallet_path, args.wallet_name))
        block = chain.produce_block(wallet.address)
        chain.save_state(path)
        print(
            json.dumps(
                {
                    "block_hash": block.block_hash,
                    "producer": wallet.address,
                    "saved_to": str(path),
                    "frontier": list(chain.frontier),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "balance":
        address = args.address or Wallet.load(_resolve_wallet_path(args.wallet_path, args.wallet_name)).address
        print(
            json.dumps(
                {
                    "address": address,
                    "balance": chain.balances().get(address, 0),
                    "path": str(path),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "load":
        print(
            json.dumps(
                {
                    "summary": chain.chain_summary(),
                    "frontier": list(chain.frontier),
                    "virtual_order": chain.virtual_order(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "show-frontier":
        print(json.dumps({"frontier": list(chain.frontier)}, indent=2, sort_keys=True))
        return

    if args.command == "show-confirmed":
        print(json.dumps({"confirmed_order": chain.confirmed_order()}, indent=2, sort_keys=True))
        return

    if args.command == "show-rewards":
        print(json.dumps({"confirmed_rewards": chain.confirmed_reward_totals()}, indent=2, sort_keys=True))
        return

    if args.command == "show-dag":
        print(json.dumps({"dag": chain.dag_summary()}, indent=2, sort_keys=True))
        return

    if args.command == "show-virtual":
        print(
            json.dumps(
                {
                    "virtual_order": chain.virtual_order(),
                    "confirmed_order": chain.confirmed_order(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "show-resolved":
        print(
            json.dumps(
                {
                    "accepted_virtual_transactions": chain.accepted_virtual_transactions(),
                    "resolved_virtual_blocks": chain.resolved_virtual_blocks(),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return

    if args.command == "show-l1-feed":
        confirmed_only = args.mode == "confirmed"
        print(
            json.dumps(
                chain.export_l1_feed(confirmed_only=confirmed_only),
                indent=2,
                sort_keys=True,
            )
        )
        return


if __name__ == "__main__":
    main()
