# Structural Cryptography

A minimal policy-enforced UTXO blockchain evolving from the original Structural Cryptography signature prototype.

## What Changed

The repository now separates three layers:

- `structural_crypto.crypto`: structure functions, policy commitments, and structure-bound signing.
- `structural_crypto.ledger`: transactions, UTXOs, PoCT DAG blocks, producer-based block formation, and chain validation.
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

## PoCT Trajectory Layer

The concrete next protocol step is the trajectory validity layer:

- per-identity `prev`
- sequence continuity
- branch-conflict detection
- identity state transitions
- rate-limit-aware legitimacy

See:

- [docs/POCT_TRAJECTORY_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TRAJECTORY_SPEC.md)

## PoCT Producer Model

The current recommended producer path is Model A:

- everyone may submit transactions
- mature identities should dominate producer influence
- producer power comes from compliant trajectory history

See:

- [docs/POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)

## PoCT Producer Gate

The current recommended enforcement rule is a hard producer gate:

- `new`: no block production
- `probation`: no normal block production
- `mature`: block production allowed
- `penalized`: block production denied

See:

- [docs/POCT_PRODUCER_GATE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PRODUCER_GATE_SPEC.md)

## PoCT Producer Selection

Once several producers are eligible, PoCT compares them by:

- phase
- ordering score
- average delta
- branch conflicts
- timestamp
- producer id

See:

- [docs/POCT_PRODUCER_SELECTION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PRODUCER_SELECTION_SPEC.md)

## PoCT L0 / L1 Boundary

The current repository should be understood as an `L0` prototype:

- legality
- trajectory continuity
- producer rules
- DAG ordering
- confirmation

Richer execution should live in `L1`, not inside the L0 core.

See:

- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)

## PoCT L1 Interface

The repository now also defines the first interface contract from the PoCT L0 legality-and-ordering layer to a future richer L1 execution layer.

See:

- [docs/POCT_L1_INTERFACE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L1_INTERFACE_SPEC.md)

## PoCT L1 Batching

The repository now also defines how confirmed `L0` history should be grouped into deterministic `L1` execution batches and future checkpoints.

See:

- [docs/POCT_L1_BATCH_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L1_BATCH_SPEC.md)

## Next-Phase Specs

The repository now also includes first-pass specifications and code skeletons for:

- multi-node PoCT networking
- zk backend integration
- stress testing
- security review preparation
- deterministic state transition review
- L1 execution consumption

See:

- [docs/POCT_NODE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_NODE_SPEC.md)
- [docs/POCT_ZK_BACKEND_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_ZK_BACKEND_SPEC.md)
- [docs/POCT_STRESS_TEST_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_STRESS_TEST_SPEC.md)
- [docs/POCT_SECURITY_AUDIT_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_SECURITY_AUDIT_SPEC.md)
- [docs/POCT_STATE_TRANSITION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_STATE_TRANSITION_SPEC.md)
- [docs/POCT_L1_EXECUTION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L1_EXECUTION_SPEC.md)

## CLI Wallet And Local Node Gossip

The prototype now also includes:

- local CLI wallet create/show flow
- transaction gossip import between local nodes
- file-spool local multi-process node testing

## GitHub Pages Wallet

The repository now also includes a static browser wallet under:

- `docs/wallet/index.html`

Once GitHub Pages is enabled for the repository `docs/` directory, the wallet page can be hosted at:

- `https://<user>.github.io/<repo>/wallet/`

To enable it on GitHub:

1. Open the repository `Settings`
2. Open `Pages`
3. Under `Build and deployment`, choose:
   - `Source`: `Deploy from a branch`
   - `Branch`: `main`
   - `Folder`: `/docs`
4. Save and wait for the Pages deployment to finish

For this repository shape, the published wallet URL should look like:

- `https://papasop.github.io/zk_structure/wallet/`

## PoCT Tokenomics

The repository now defines a first-stage issuance direction for PoCT:

- declining emissions
- fixed low tail emission

See:

- [docs/POCT_TOKENOMICS_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TOKENOMICS_SPEC.md)

## PoCT Persistence

The current prototype now includes:

- JSON state export
- file-based save/load
- CLI state inspection commands

See:

- [docs/POCT_PERSISTENCE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PERSISTENCE_SPEC.md)

## PoCT Repository Governance

The repository now also defines a governance model for code contribution, review, and merge authority in environments with many contributors, including AI agents.

See:

- [docs/POCT_REPO_GOVERNANCE.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_REPO_GOVERNANCE.md)
