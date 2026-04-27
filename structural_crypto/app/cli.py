"""CLI for the minimal Structural Cryptography blockchain."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from structural_crypto.app.demo import build_demo_chain, run_demo
from structural_crypto.ledger.blockchain import Blockchain


def _resolve_state_path(path_arg: str | None) -> Path:
    if path_arg:
        return Path(path_arg)
    return Blockchain.default_state_path()


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="structural-chain",
        description="Minimal policy-enforced UTXO blockchain built from Structural Cryptography.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo", help="run the built-in blockchain demo")

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

    args = parser.parse_args()
    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, sort_keys=True))
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
