# PoCT L0 / L1 Specification v0.1

## Goal

This document fixes the architectural boundary between:

- `L0`: the PoCT legality-and-ordering layer
- `L1`: higher-level execution and application logic

The purpose is to preserve the defining property of PoCT:

> legality is decided before general-purpose execution.

## Core Principle

PoCT-L0 is **not** a traditional smart-contract VM layer.

PoCT-L0 is responsible for:

- identity entry and maturation
- trajectory legitimacy
- producer eligibility
- producer ordering
- DAG acceptance
- virtual ordering
- confirmation / finality
- confirmed reward accounting

PoCT-L1 is responsible for:

- richer application logic
- arbitrary state machines
- contract execution
- complex cross-user application semantics

## Why This Boundary Matters

If L0 is allowed to become a general-purpose execution VM:

- execution metering returns
- gas-like pricing returns
- PoCT legality becomes entangled with arbitrary code paths
- the architecture starts collapsing back into a conventional chain

So the correct design is:

- keep L0 narrow, strict, and legality-focused
- place rich execution above it

## What Belongs in L0

The following belong in L0:

### 1. Identity and Cold Start

- `new / probation / mature / penalized`
- external bootstrap credential inputs
- ordering score growth

### 2. Trajectory Legitimacy

- `trajectory_id`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `delta`
- continuity validation
- branch conflict detection
- rate-limit enforcement

### 3. Producer Rules

- producer gate
- producer selection
- producer conflict penalties

### 4. DAG Ordering

- `parents[]`
- frontier maintenance
- virtual order
- cross-block conflict resolution
- confirmation score and finality

### 5. Protocol-Level Reward Accounting

- reward only for confirmed blocks
- reward scaled by producer maturity / score

## What Does Not Belong in L0

The following should not be native L0 responsibilities:

- unrestricted general-purpose contracts
- arbitrary VM execution
- opcode-level gas accounting
- DeFi-style execution graphs
- application-specific state explosion
- complex programmable composability

These are L1 concerns.

## L0 Contract Model

If L0 has "contracts", they should be understood as:

- policy-native templates
- trajectory-native transition rules

Examples:

- amount-capped transfer
- whitelist-constrained transfer
- time-window rate limit
- cumulative trajectory allowance
- simple bilateral commitment updates

These are not arbitrary programs.
They are constrained state transition templates.

## Why L0 Can Be Gasless

PoCT-L0 can be called "gasless" only in the following sense:

- it avoids a general-purpose execution VM
- it does not meter arbitrary opcode execution
- legality is checked through protocol rules rather than general scripting

This does **not** mean the system has zero resource cost.
It means L0 avoids the classic gas model of VM execution metering.

## L1 Role

L1 is where richer programmability should live.

Possible L1 roles:

- application rollups
- zk application state machines
- app-specific execution environments
- contract systems with more expressive logic

L1 should consume finalized ordering and validity from L0 rather than redefine legality itself.

## Relationship Between L0 and L1

The recommended relationship is:

1. L0 decides whether actions are admissible
2. L0 orders admissible actions
3. L0 confirms producer history
4. L1 executes higher-level application logic on top of that ordered admissible stream

So the layering is:

- `L0 = admissibility + ordering + finality`
- `L1 = expressive execution`

## Why This Fits the Current Repository

The current repository already implements major L0 components:

- trajectory-aware ledger
- producer gate
- producer selection
- DAG block structure
- virtual order
- confirmation / finality
- confirmed reward accounting
- cross-block conflict resolution

That means the current codebase should continue deepening the L0 role, not collapse into a general VM too early.

## Recommended Next Architectural Rule

Use this design constraint going forward:

> If a feature can be expressed as legality, continuity, ordering, or confirmation, it belongs in L0.
> If it requires arbitrary application execution, it belongs in L1.

## Migration Path

### Current Stage

- single-process PoCT-DAG prototype
- L0 legality and ordering skeleton

### Next Stage

- stronger L0 conflict handling
- better reward settlement
- persistent DAG state

### Later Stage

- explicit L1 interface
- application execution layer
- possible zk-backed state transition layer above L0

## Repository Linkage

This specification consolidates the meaning of all current protocol documents:

- [docs/POCT_COLD_START.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_COLD_START.md)
- [docs/POCT_TRAJECTORY_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TRAJECTORY_SPEC.md)
- [docs/POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)
- [docs/POCT_PRODUCER_GATE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PRODUCER_GATE_SPEC.md)
- [docs/POCT_PRODUCER_SELECTION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PRODUCER_SELECTION_SPEC.md)
- [docs/POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)

It defines how they fit into a long-term layered architecture.
