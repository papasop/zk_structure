# BBS-DAG Deployment Status

## Goal

Keep the deployment story honest by separating:

- what the current repository already implements
- what the target network version is expected to implement later

This prevents prototype documentation from being read as production readiness.

## Minimal Mainline

The current implementation roadmap is intentionally frozen to:

1. `identity`
2. `trajectory`
3. `DAG ordering`
4. `finality`
5. `finalized L1 batch`

The following are explicitly deferred:

- GPU proving
- proof aggregation
- DSL-based contract authoring
- Docker-first production orchestration
- Rust full-node rewrite

## Current Versus Target

| Area | Current Repository (`implemented now`) | Target Version (`not implemented yet`) |
| --- | --- | --- |
| Node runtime | Python prototype node with local RPC, gossip spool, DAG sync | Dedicated production node runtime, likely Rust or mixed-language |
| Consensus core | Identity maturation, trajectory validation, producer gating, DAG ordering, confirmation | Full network finality with live voting, pacemaker, anti-equivocation penalties |
| Finality | Finality data model skeleton, deterministic checkpoints, finalized batch export, finality RPC surface | Real committee vote exchange, lock/finalize certificates from distributed peers |
| Execution boundary | `L0` legality and ordering plus toy `L1` batch consumer | Rich `L1` execution engine with settlement and proof pipelines |
| ZK backend | Mock / placeholder integration points | Real PLONK or equivalent proving and verification backend |
| Contracts | Policy-constrained transaction model | Circuit registry, contract lifecycle, user-defined zk contracts |
| Networking | Local peer model, RPC reconciliation, file-spool gossip testing | Internet-grade peer discovery, anti-entropy, robust transport, sybil-hardening |
| Persistence | JSON state save/load | Durable indexed storage, snapshotting, pruning, finalized checkpoint persistence |
| Tooling | Python CLI demo and tests | User-facing wallet tooling, ops CLI, production key management |
| Deployment | Local development and test execution | Container images, orchestration, observability bundles, production runbooks |

## What “Deployable” Means Right Now

Today this repository is suitable for:

- local protocol iteration
- deterministic test scenarios
- multi-node sync experiments
- `L0` / `L1` interface prototyping

It is not yet suitable for:

- public production deployment
- GPU-backed proving benchmarks
- audited smart-contract hosting
- trust-minimized permissionless operation on hostile networks

## Immediate Next Milestones

1. Turn finality skeletons into persisted state and cross-peer verification flows.
2. Make finalized checkpoints the default handoff boundary for `L1`.
3. Expand tests from local deterministic finality to peer-exchanged finality evidence.
4. Only after that, revisit real ZK backend integration and production deployment packaging.
