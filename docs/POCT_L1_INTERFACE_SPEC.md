# PoCT L1 Interface Specification v0.1

## Goal

This document defines the interface between:

- `L0`: the PoCT legality-and-ordering layer
- `L1`: the richer execution layer

The purpose is to ensure that:

- L0 remains narrow and legality-focused
- L1 remains expressive without redefining L0 admissibility

## Core Principle

L1 does **not** decide whether an action is admissible.

L0 decides:

- whether an action is allowed to exist
- whether it is trajectory-legitimate
- whether it survives ordering
- whether it becomes confirmed

L1 consumes the ordered admissible stream and applies richer execution logic on top.

## L0 -> L1 Output

L0 should expose a finalized admissible stream.

At minimum, L1 needs:

### 1. Ordered Transaction Stream

A deterministic ordered list of accepted L0 transactions.

This stream must already reflect:

- virtual ordering
- cross-block conflict resolution
- confirmation / finality filtering

### 2. Transaction Metadata

Each L1-visible transaction should carry:

- `txid`
- `sender`
- `trajectory_id`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `delta`
- outputs / transferred values

This lets L1 reason about higher-level application semantics while preserving the L0 legality context.

### 3. Confirmation Boundary

L1 should know which L0 transactions are:

- only accepted
- ordered
- confirmed

For state transition safety, L1 should normally consume **confirmed** L0 order, not merely tentative DAG order.

### 4. Producer / Provenance Context

Optional but useful metadata:

- producer id
- producer phase
- producer ordering score
- block hash / parent references

This allows L1 or external observers to reason about how execution inputs entered the system.

## L1 Responsibilities

L1 may implement:

- richer state machines
- application contracts
- rollup logic
- zk application execution
- generalized app-level transitions

L1 should **not** redefine:

- trajectory legitimacy
- producer eligibility
- L0 conflict rules
- L0 finality definition

Those remain L0 concerns.

## Allowed L1 Input Modes

The interface can support several modes:

### Mode A: Confirmed Stream Input

L1 consumes only confirmed L0 transactions.

Best for:

- correctness-first execution
- stable application state

Tradeoff:

- higher latency

### Mode B: Ordered-but-Not-Final Input

L1 consumes virtual-order output before full confirmation.

Best for:

- preview state
- optimistic UX

Tradeoff:

- possible reordering risk until finality

### Mode C: Batch Snapshot Input

L1 periodically consumes a batch of already confirmed L0 order.

Best for:

- rollups
- periodic proving systems
- checkpointed app execution

## Why L0 Can Stay Gasless

The L0 gasless claim remains meaningful only if:

- L0 does not run a general-purpose execution VM
- L0 does not meter arbitrary opcode execution
- L0 stays focused on legality and ordering

L1 may still need its own execution cost model.

So the architectural statement is:

- `L0` may be gasless in the VM-metering sense
- `L1` may have execution pricing or proving cost

These do not conflict.

## L1 Execution Envelope

L1 should treat L0 as its admissibility substrate.

That means:

- L0 determines which actions may enter
- L1 determines what those actions mean at the app layer

Example:

- L0 says a capped transfer is admissible
- L1 interprets that transfer as part of a richer application state transition

## Forbidden L1 Behavior

L1 must not:

- accept actions that L0 rejected
- silently reorder confirmed L0 history
- ignore L0 conflict resolution
- bypass L0 producer/finality outputs when claiming canonical execution

If L1 needs broader expressiveness, it may add logic above L0, but not replace L0's legality decisions.

## Suggested Interface Shape

A minimal L0 -> L1 interface should expose:

- `confirmed_order()`
- `accepted_virtual_transactions()`
- `resolved_virtual_blocks()`
- per-transaction metadata
- per-block producer metadata

These already align well with the current prototype structure.

## L1 State Checkpointing

L1 should periodically anchor:

- execution state root
- batch boundary
- corresponding L0 confirmation range

This keeps L1 execution tied to an explicit slice of confirmed L0 history.

## Future Extension

Later versions may add:

- explicit `export_l1_feed()` helper
- batch checkpoints
- state root commitments
- proof-carrying L1 execution outputs

But the first rule should remain unchanged:

> L0 decides admissibility and order; L1 decides rich execution meaning.

## Repository Linkage

This document extends:

- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)

It describes how the current L0 prototype should feed a future execution layer without collapsing the L0/L1 boundary.
