# PoCT L1 Batch Specification v0.1

## Goal

This document defines how confirmed `L0` history is grouped into consumable `L1` batches.

It extends the earlier interface goal:

- `L0` decides admissibility
- `L0` decides ordering
- `L0` decides confirmation
- `L1` consumes confirmed history in explicit batches

The purpose of the batch layer is to avoid treating `L1` as an ad hoc reader of raw confirmed blocks.

## Core Principle

`L1` should not pull arbitrary fragments of `L0` history and guess execution boundaries.

Instead, `L0` should expose explicit batch units with:

- a deterministic range
- a deterministic digest
- a deterministic ordered transaction list

This makes later checkpointing, settlement, and proof generation stable.

## Batch Input

A PoCT `L1` batch is built from the `confirmed` subset of the resolved virtual order.

That means a valid batch must already reflect:

- DAG virtual ordering
- cross-block conflict resolution
- confirmation / finality filtering

The batch input is therefore downstream of `L0` legality, not parallel to it.

## Batch Boundary

The minimal model for `v0.1` is:

- a batch is a contiguous slice of `confirmed_order()`

Examples:

- genesis-only batch
- first `N` confirmed blocks
- confirmed blocks since the last exported checkpoint

The key requirement is determinism:

two nodes with the same confirmed `L0` state must produce the same batch boundary.

## Batch Contents

Each exported batch should contain:

### 1. Batch Metadata

- `batch_id`
- `batch_start`
- `batch_end`
- `batch_size`
- `mode`

### 2. Ordered Block Context

For each included confirmed block:

- `block_hash`
- `parents`
- `producer_id`
- `producer_phase`
- `producer_ordering_score`
- `confirmed_reward`

### 3. Ordered Accepted Transactions

For each included accepted transaction:

- `txid`
- `sender`
- `trajectory_id`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `delta`
- `inputs`
- `outputs`
- `block_hash`

### 4. Batch Digest

A single deterministic digest over:

- the ordered confirmed block hashes
- the ordered accepted transaction ids
- batch boundary metadata

This digest allows later checkpoint anchoring and state synchronization.

## Batch ID

`batch_id` should be stable and deterministic.

For `v0.1`, the simplest rule is:

- `batch_id = hash(batch_start || batch_end || batch_digest)`

Where:

- `batch_start` and `batch_end` refer to positions in the confirmed block order
- `batch_digest` commits to the actual ordered contents

## Batch Digest

The digest should commit to:

- ordered confirmed block hashes
- ordered accepted transaction ids
- ordered producer metadata

The digest is not a replacement for block hashes.

It is a higher-level commitment to the exact slice exported to `L1`.

## Batch Export Modes

### Mode A: Full Confirmed Batch

Exports:

- all currently confirmed blocks
- all accepted transactions inside them

Best for:

- prototype execution layers
- simple off-chain consumers

### Mode B: Incremental Batch

Exports:

- only confirmed blocks after the last settled batch

Best for:

- long-running `L1` engines
- checkpointed pipelines

### Mode C: Fixed Window Batch

Exports:

- a selected contiguous confirmed range

Best for:

- proving systems
- backfill
- replay

## Checkpoint Output

After consuming a batch, `L1` should be able to produce:

- `batch_id`
- optional `l1_state_root`
- optional `execution_digest`
- optional `proof_reference`

This does **not** change `L0` legality.

It simply records what richer execution meaning was derived from the confirmed `L0` slice.

## Settlement Semantics

The minimal settlement model is:

- `L0` exports a confirmed batch
- `L1` consumes it
- `L1` may publish a checkpoint artifact

Future versions may let `L0` anchor that checkpoint, but `v0.1` only requires the interface shape.

## Replay and Idempotence

A correct batch export must be replayable.

That means:

- exporting the same confirmed range twice yields the same batch digest
- `L1` can detect duplicate consumption by `batch_id`

This is important for:

- crash recovery
- multi-node execution
- proof retries

## Relation to Gaslessness

This batch layer preserves the earlier architectural claim:

- `L0` stays gasless in the sense of avoiding general-purpose VM metering
- `L1` may still have execution cost, proving cost, or application-level pricing

Batching does not move general execution into `L0`.

It only structures the confirmed admissible stream for safe consumption.

## Suggested Code Shape

The current prototype already exposes:

- `confirmed_order()`
- `confirmed_l1_batch()`
- `export_l1_feed()`

The next evolution should add:

- explicit batch range arguments
- `batch_digest`
- optional `last_exported_checkpoint`
- later, `l1_state_root` anchoring

## Repository Linkage

This document extends:

- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)
- [docs/POCT_L1_INTERFACE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L1_INTERFACE_SPEC.md)

It narrows the `L0 -> L1` interface from a generic feed into a deterministic batch/checkpoint model.
