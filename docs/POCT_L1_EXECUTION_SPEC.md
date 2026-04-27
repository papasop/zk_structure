# PoCT L1 Execution Specification v0.1

## Goal

Define the first executable consumer of confirmed PoCT L0 batches.

## Minimal Executor

- consumes `confirmed_l1_batch()`
- applies ordered accepted transactions
- produces `state_root`
- produces `batch_id`

## First Required Tests

- replay same batch twice yields same batch digest
- identical inputs yield identical state root
- reordered inputs yield different batch digest

## Deferred

- proof-carrying execution
- on-L0 checkpoint anchoring
- rich smart contract semantics
