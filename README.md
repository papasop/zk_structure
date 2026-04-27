# Structural Cryptography

A minimal policy-enforced UTXO blockchain evolving from the original Structural Cryptography signature prototype.

## What Changed

The repository now separates three layers:

- `structural_crypto.crypto`: structure functions, policy commitments, and structure-bound signing.
- `structural_crypto.ledger`: transactions, UTXOs, blocks, proof-of-work mining, and chain validation.
- `structural_crypto.app`: a tiny CLI and an end-to-end demo.
- `structural_crypto.consensus`: PoCT cold-start and identity maturation helpers.

This first implementation is intentionally small:

- single-process blockchain
- UTXO ledger
- proof-of-work block production
- policy-enforced transaction admission
- no external dependencies

## Repository Layout

```text
structural_crypto/
  crypto/
  ledger/
  node/
  app/
tests/
PoRC.pdf
```

## Quick Start

```bash
python3 -m unittest discover -s tests
python3 -m structural_crypto.app.cli demo
```

Or install the package locally and use the CLI entry point:

```bash
pip install -e .
structural-chain demo
```

## Design Notes

Transactions are accepted only when all of the following hold:

1. referenced UTXOs exist and belong to the sender
2. outputs do not exceed inputs
3. the structure signature verifies
4. the residual `delta` stays below the policy `epsilon`
5. optional policy rules such as recipient allowlists or amount caps are satisfied

That makes the first blockchain version align with the original research direction:

> transaction validity is not just ownership, but ownership plus behavior constraints.

## Next Steps

- replace the simplified signature flow with a real ZK backend
- add persistent chain storage
- introduce per-identity history and rate-limit rules
- evolve from a linear chain to DAG ordering if the research path still points there

## PoCT Cold Start

This repository now includes a first PoCT cold-start model:

- open entry
- low initial ordering power
- trajectory-based maturation
- optional capped external credential boost

See:

- [docs/POCT_COLD_START.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_COLD_START.md)
- [structural_crypto/consensus/cold_start.py](/Users/bai/Documents/New%20project/zk_structure/structural_crypto/consensus/cold_start.py)

## PoCT-DAG Direction

The next protocol layer is a DAG ordering model inspired by the shape of Kaspa's parallel block graph, but rooted in PoCT legitimacy rather than `PoW`.

See:

- [docs/POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)
