# PoCT Sync And Convergence Specification v0.1

## Goal

Define how independent PoCT nodes should exchange enough information to converge on:

- the same visible DAG block set
- the same virtual order
- the same confirmed order

This document sits between the high-level DAG design and the concrete node skeleton.

## Why This Spec Is Needed

The current repository already defines:

- legality rules
- trajectory rules
- producer eligibility
- DAG block structure
- local node RPC/gossip skeletons

What was still implicit is the convergence contract:

- what a node must summarize to peers
- how missing history is fetched
- when local order may be recomputed
- which invariants indicate successful sync

Without that layer, two honest nodes may both be valid but still lack a clear rule for when they should agree.

## Design Principle

PoCT sync should be:

1. block-set convergent before state convergent
2. deterministic after import
3. lightweight in `v0.1`
4. extensible toward anti-entropy and richer peer discovery later

In short:

`exchange summaries -> fetch missing blocks -> import parents first -> recompute virtual order -> compare confirmed order`

## Convergence Targets

Two honest nodes are considered converged for `v0.1` when all of the following hold:

1. they know the same accepted block hashes
2. they expose the same frontier set
3. they derive the same virtual order from that block set
4. they derive the same confirmed order under the same confirmation threshold

UTXO state, rewards, and future `L1` feeds are downstream consequences of those four conditions.

## Local Node Views

Every node should maintain at least these views:

- `known_blocks`
- `frontier`
- `virtual_order`
- `confirmed_order`
- `confirmation_threshold`

In `v0.1`, these views are enough to reason about sync success without introducing full state snapshots as the normal sync path.

## Required Summary Exchange

A minimal sync summary should contain:

- `node_id`
- `frontier`
- `known_blocks`
- `confirmed_order`
- optional `virtual_order`
- optional config digest for sync-critical parameters

### Summary Intuition

- `frontier`
  Tells a peer where your visible DAG currently ends.
- `known_blocks`
  Lets a peer quickly decide whether frontier blocks are actually missing or already reachable.
- `confirmed_order`
  Gives an early convergence signal even before full diagnostic tooling exists.
- `config digest`
  Prevents silent disagreement caused by mismatched confirmation thresholds or other ordering-critical settings.

## Sync-Critical Configuration

Nodes must not assume convergence if they disagree on:

- `confirmation_threshold`
- producer ordering comparator inputs
- trajectory validity rules
- block acceptance rules

For `v0.1`, the simplest rule is:

- if sync-critical config differs, nodes may exchange data
- but they must mark the peer as `non-comparable` for confirmation convergence

## Initial Sync Flow

When node `A` reconciles with node `B`, the required flow is:

1. request `B`'s sync summary
2. compare `frontier` against `A`'s known block set
3. mark missing frontier blocks
4. fetch each missing block
5. recursively fetch missing parents first
6. import fetched blocks
7. recompute virtual order
8. recompute confirmed order
9. compare resulting frontier and confirmed order to the peer view

This matches the current prototype shape and keeps the first implementation simple.

## Parent-First Import Rule

A node must not finalize local import of a block before all referenced parents are locally known.

Allowed implementation behavior:

- recursive parent fetch
- iterative missing-parent queue
- temporary staging area before final acceptance

The required invariant is simply:

- no accepted local block may reference an unknown parent

## Virtual Order Recalculation

After any successful block import, the node must treat:

- frontier
- virtual order
- confirmed order

as potentially stale derived views.

The implementation may recompute eagerly after each import or lazily after a batch, but the observable result must be deterministic from the accepted block set.

## Confirmation Recalculation

Confirmation is not synchronized directly as a trust input.
It is synchronized indirectly by importing the same accepted block set and running the same deterministic rule.

That means:

- peers may share `confirmed_order` as a diagnostic view
- peers must not accept `confirmed_order` by authority alone

Instead, each node should recompute confirmation locally after sync.

## Honest Convergence Rule

If two honest nodes have:

- the same sync-critical config
- the same accepted block set
- the same deterministic ordering rule

then they must derive:

- the same virtual order
- the same confirmed order

If they do not, that is a protocol bug, not a normal network condition.

## Divergence Cases

`v0.1` should explicitly distinguish three cases:

### 1. Missing Data Divergence

The peer knows blocks we do not yet know.

Expected action:

- fetch missing blocks and parents

### 2. Temporary Frontier Divergence

Both nodes are valid but have seen different recent tips.

Expected action:

- exchange frontier summaries
- import missing blocks
- recompute order

### 3. Non-Comparable Divergence

Nodes disagree after import despite sharing the same visible block set, or they run different sync-critical configs.

Expected action:

- flag diagnostic failure
- do not claim confirmation convergence
- preserve both local states for audit

## Gossip Versus Reconciliation

PoCT should keep two separate network behaviors:

- gossip
- reconciliation

### Gossip

Used for low-latency propagation of:

- transactions
- newly produced blocks

Gossip is optimistic and may arrive out of order.

### Reconciliation

Used for correctness recovery when peers may have missed messages.

Reconciliation is summary-driven and must be able to restore convergence even if earlier gossip was lost.

This separation keeps the system robust without making every gossip message a full sync protocol.

## Minimal RPC Surface

The current recommended RPC surface for `v0.1` is:

- `get_sync_summary`
- `get_block`
- `get_confirmed`
- optional `get_frontier`
- optional `get_l1_feed`

### Semantics

- `get_sync_summary`
  Returns the peer's current convergence summary.
- `get_block`
  Returns a concrete block by hash for missing-history fetch.
- `get_confirmed`
  Returns a diagnostic confirmation view.

`get_block` is the only RPC that transfers authoritative history objects.

## Frontier Semantics

`frontier` should be interpreted as:

- accepted blocks with no accepted local children currently known

It is a local DAG boundary, not a statement of finality.

Two peers may temporarily expose different frontier sets during propagation delay without either peer being invalid.

## Persisted State Requirements

Persisted local state should preserve enough information to restart sync without replay ambiguity:

- accepted block set
- frontier
- sender trajectory state
- identity state
- sync-critical config

After reload, a node should be able to:

1. answer summary RPCs
2. fetch blocks for peers
3. reconcile with peers
4. recompute virtual and confirmed order deterministically

## Test Matrix

The next multi-node tests should cover at least:

1. peer `A` produces blocks while peer `B` is offline
2. `B` reconnects and imports missing parents recursively
3. both peers reach identical frontier
4. both peers reach identical confirmed order
5. persisted reload does not change convergence outcome
6. mismatched confirmation thresholds are detected as non-comparable

## Deferred Work

This spec intentionally defers:

- peer discovery
- header-only sync
- compact block relay
- anti-entropy rounds
- Byzantine peer scoring
- checkpoint-assisted fast sync

Those belong to `v0.2+` once the deterministic `v0.1` convergence path is stable.

## Implementation Guidance

The current repository can implement this spec incrementally:

1. add a sync-critical config digest to node summaries
2. expose a direct convergence check helper
3. expand tests from missing-block import to confirmed-order equivalence
4. add explicit diagnostics for non-comparable peers

## Repository Role

This specification is the bridge between:

- [POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)
- [POCT_NODE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_NODE_SPEC.md)
- [POCT_STATE_TRANSITION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_STATE_TRANSITION_SPEC.md)

It defines how independent local views become one shared deterministic ledger view without introducing PoW or stake-weighted finality.
