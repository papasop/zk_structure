"""CLI for the minimal Structural Cryptography blockchain."""

from __future__ import annotations

import argparse
import json

from structural_crypto.app.demo import run_demo


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="structural-chain",
        description="Minimal policy-enforced UTXO blockchain built from Structural Cryptography.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("demo", help="run the built-in blockchain demo")

    args = parser.parse_args()
    if args.command == "demo":
        print(json.dumps(run_demo(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

