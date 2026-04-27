# PoCT-DAG Specification v0.1

## Goal

PoCT-DAG borrows the structural idea of a `blockDAG`: multiple valid blocks may exist in parallel and later be ordered into a shared ledger view.

Unlike Kaspa, PoCT-DAG does **not** use `PoW` as its security root.
Its security root is:

- signature validity
- policy validity
- trajectory validity
- compliance-weighted ordering

In short:

`Kaspa = DAG + PoW ordering`

`PoCT-DAG = DAG + compliant-trajectory ordering`

## Design Principle

The system separates **acceptance** from **ordering**:

1. a transaction must first be locally acceptable
2. acceptable transactions may appear in parallel blocks
3. the DAG ordering layer determines final sequence among acceptable blocks

That means ordering cannot turn an invalid action into a valid one.

## Block Format

Each block contains:

- `block_id`
- `parents[]`
- `timestamp`
- `producer_id`
- `producer_phase`
- `transactions[]`
- `producer_ordering_score`
- `aggregate_delta`
- `trajectory_commitment`
- `virtual_order_hint`

### Field Intuition

- `parents[]`
  Multiple parent references allow parallel block production.
- `producer_id`
  The PoCT identity responsible for the block.
- `producer_phase`
  One of `new`, `probation`, `mature`.
- `producer_ordering_score`
  The producer's current PoCT ordering score.
- `aggregate_delta`
  Average or weighted delta summary of included transactions.
- `trajectory_commitment`
  Commitment to the producer's own trajectory head when producing this block.
- `virtual_order_hint`
  Optional deterministic tie-break helper for local ordering.

## Transaction Admission

A transaction may enter the DAG only if all checks pass:

1. signature validity
2. policy validity
3. trajectory continuity
4. no branch conflict
5. rate-limit validity
6. balance / state validity

This is stricter than ordinary mempool admission because PoCT-DAG treats the trajectory itself as part of ledger validity.

## Trajectory Rule

Each identity maintains a single active trajectory.

Each transaction must include:

- `prev`
- `epoch`
- `sequence`
- `trajectory_id`
- `delta`
- `policy_hash`

### Validity

A transaction is trajectory-valid if:

- `prev` points to the unique prior accepted action of that identity
- `sequence` increments by one
- `trajectory_id` matches the identity's active trajectory
- the action does not violate time-window or cumulative policy constraints

## Branch Conflict Rule

A branch conflict occurs when an identity attempts any of the following:

- two distinct transactions referencing the same `prev`
- two competing transactions with the same `(identity, sequence)`
- a state transition that skips the expected predecessor

Branch conflicts do not merely reduce priority.
They reduce trust in the producer and can block maturation.

## DAG Parent Selection

A new block should reference:

1. the producer's preferred ordered parent
2. additional visible frontier parents
3. optional anti-isolation parents that help merge concurrent views

The objective is not longest-chain growth.
The objective is rapid convergence over a parallel set of acceptable blocks.

## Ordering Score

PoCT-DAG replaces work weight with compliance weight.

The ordering score of a producer is derived from:

- cold-start phase
- compliant transaction count
- average delta quality
- branch conflict penalty
- rejection rate
- optional capped external bootstrap evidence

This score is already modeled in:

- [structural_crypto/consensus/cold_start.py](/Users/bai/Documents/New%20project/zk_structure/structural_crypto/consensus/cold_start.py)

## Block Ordering Rule

When two or more acceptable blocks compete for earlier placement, prefer the block whose producer has:

1. higher PoCT ordering score
2. lower recent aggregate delta
3. stronger parent connectivity to the current virtual frontier
4. earlier timestamp within a bounded skew window
5. deterministic lexical tie-break on `block_id`

This yields a deterministic local policy without requiring PoW.

## Virtual Main Order

PoCT-DAG should maintain a deterministic virtual order over the DAG.

The virtual order is not a single mined chain.
It is a derived ordering view computed from:

- currently visible frontier
- parent connectivity
- producer compliance score
- conflict exclusions

The virtual order serves the role of:

- confirmation order
- state application order
- reward accounting order

## Confirmation Rule

A transaction is considered:

- `accepted` once it appears in a valid PoCT block
- `ordered` once included in the virtual main order
- `confirmed` once enough later high-score DAG mass builds on blocks that preserve its placement

The exact confirmation threshold can be tuned later.
The important part now is the separation:

- local validity
- global ordering
- final confidence

## Reward Policy

Rewards should not be granted purely for block count.

Recommended rule:

- reward only ordered blocks
- scale reward by producer maturity and score
- reduce reward for producers with branch conflicts
- optionally share reward with compliant transaction originators

This prevents trivial block spam from immature identities.

## Why This Is Not PoW

PoCT-DAG does not ask:

- who performed more work
- who owns more stake

It asks:

- whose trajectory is more continuously compliant
- whose recent behavior is lower-risk
- whose history is less conflicted

That is the core shift from resource legitimacy to behavioral legitimacy.

## Recommended Implementation Order

1. add trajectory fields to transactions
2. add branch-conflict detection
3. add per-identity trajectory head tracking
4. add DAG block structure with multi-parent references
5. add virtual ordering over the DAG
6. connect rewards to ordered compliant blocks

## Current Repository Boundary

This specification is the next protocol step after:

- [docs/POCT_COLD_START.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_COLD_START.md)

The repository does **not** yet implement full DAG ordering.
This document defines the next design target.
