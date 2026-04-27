# PoCT Repository Governance v0.1

## Goal

This document defines repository governance for a development environment where:

- many contributors may participate
- AI agents may propose frequent code changes
- protocol-critical files cannot be treated like ordinary application code

The governance model follows PoCT principles, but it is **not** identical to on-chain reward or block-production logic.

## Core Principle

Repository governance should follow the same high-level philosophy as PoCT:

- influence should not come from raw volume
- new participants should not receive immediate critical authority
- trust should grow through stable, compliant contribution history
- conflicts and unsafe changes should reduce authority

But repository governance operates on:

- code changes
- protocol documents
- merge rights

rather than:

- transactions
- blocks
- DAG ordering

So repository governance is a **development-layer mirror** of PoCT, not a direct copy of chain logic.

## Governance Layers

There are three governance layers:

### 1. Proposal Rights

Who may suggest or submit changes.

Default rule:

- broadly open
- human contributors allowed
- AI agents allowed
- experimental contributors allowed

Proposal rights should be the most open layer.

### 2. Change Rights

Who may modify specific risk zones of the repository.

These rights should depend on:

- contribution maturity
- change type
- affected files

### 3. Merge Rights

Who may land changes into protected branches such as `main`.

Merge rights should be the narrowest layer.

## Why This Differs From On-Chain PoCT

On-chain PoCT governs:

- who may produce blocks
- how blocks are ordered
- how rewards are earned

Repository governance governs:

- who may change protocol rules
- who may alter implementation details
- who may merge critical updates

So the governance target is different:

- chain PoCT protects runtime history
- repo governance protects future protocol evolution

## Repository Risk Zones

The repository should be treated as multiple risk zones.

### Low-Risk Zone

Examples:

- README wording
- examples
- non-normative explanatory docs
- CLI help text

Expected governance:

- easier review
- broader contributor access

### Medium-Risk Zone

Examples:

- demo code
- CLI utilities
- non-consensus support code

Expected governance:

- tests should pass
- at least one review

### High-Risk Zone

Examples:

- `structural_crypto/ledger/`
- `structural_crypto/consensus/`
- persistence format logic
- `docs/POCT_*` protocol documents

Expected governance:

- stricter review
- protocol/documentation sync required
- migration note required when schema changes

## Contributor Maturity Model

Use a maturity model similar in spirit to PoCT:

- `new`
- `probation`
- `mature`
- `penalized`

### `new`

May:

- propose changes
- improve docs
- work in low-risk areas

May not:

- directly merge to protected branches
- modify critical consensus or persistence behavior without review

### `probation`

May:

- contribute implementation changes
- work in medium-risk areas
- submit protocol-related proposals

Restrictions:

- high-risk changes require stronger review

### `mature`

May:

- work in critical areas
- approve higher-risk changes
- participate in merge decisions

Restrictions:

- critical changes still require process, not personal discretion

### `penalized`

Applied when a contributor repeatedly causes:

- unsafe protocol drift
- tests broken on protected paths
- undocumented schema changes
- repeated mismatch between code and spec

Effects:

- reduced critical-area authority
- reduced merge authority

## Change Categories

Every change should be classified.

Recommended categories:

- `docs`
- `impl`
- `proto`
- `critical`
- `test`
- `refactor`

### `docs`

Documentation-only changes that do not alter normative protocol meaning.

### `impl`

Implementation changes that preserve protocol meaning.

### `proto`

Changes that alter or clarify protocol semantics.

### `critical`

Changes affecting:

- ledger logic
- producer rules
- virtual ordering
- finality
- conflict resolution
- persistence schema

### `test`

Test-only changes.

### `refactor`

Structural code cleanup that should preserve behavior.

## Merge Requirements

Recommended requirements by category:

### `docs`

- basic review

### `impl`

- tests pass
- one review

### `proto`

- tests pass
- protocol docs updated
- one strong review

### `critical`

- tests pass
- protocol docs updated
- persistence impact checked
- migration note if state format changes
- stronger review threshold

## Special Rules For AI-Agent Contributions

In a high-AI-contributor environment, the most important rule is:

> proposal access may be broad, but merge influence must remain scarce.

Therefore:

- AI agents may propose patches widely
- AI agents should not receive automatic critical merge authority
- AI-generated changes to high-risk zones must be reviewed as if they were adversarial until proven stable

The danger is not that AI writes code.
The danger is high-frequency protocol drift through many small unreviewed changes.

## Required Synchronization Rules

If a change affects protocol behavior, it must also update the relevant spec.

Examples:

- trajectory legality change -> update trajectory spec
- producer rule change -> update producer spec
- persistence layout change -> update persistence spec

This repository should reject code/spec divergence on critical paths.

## Persistence and Migration Rule

Any change affecting serialized state must include:

- impact statement
- migration note or explicit declaration of incompatibility

This is mandatory because persisted L0 state is now part of real node behavior.

## Protected Branch Rule

Recommended policy for `main`:

- must stay runnable
- tests must pass
- no unresolved critical drift
- no direct unsafe edits to core PoCT files without review discipline

## Practical Interpretation

This governance model is **aligned** with PoCT, but not **identical** to chain reward logic.

Similarity:

- maturity-based influence
- conflict-driven penalty
- history-based trust

Difference:

- repository governance controls protocol evolution
- chain governance controls runtime ledger history

So the rule is:

> same principles, different mechanics.

## Repository Linkage

This governance document complements the protocol documents by controlling how they evolve.

It is especially relevant to:

- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)
- [docs/POCT_PERSISTENCE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PERSISTENCE_SPEC.md)

because those areas sit near the highest-risk protocol boundary.
