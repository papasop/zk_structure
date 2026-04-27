# PoCT Producer Gate Specification v0.1

## Goal

This document converts the producer model into a hard admission rule.

The purpose is simple:

- not every identity that can submit transactions should be able to produce blocks
- producer power must be delayed until the identity has accumulated enough compliant trajectory history

## Default Rule

Under the default PoCT gate:

- `new`: cannot produce blocks
- `probation`: cannot normally produce blocks
- `mature`: can produce blocks
- `penalized`: cannot produce blocks

This is intentionally strict.
It prevents large numbers of fresh AI-agent identities from immediately entering the ordering layer.

## Why A Hard Gate First

Before full DAG ordering exists, the most important protection is:

- stop immature identities from gaining consensus influence too early

This is more important than building a refined producer competition rule too early.

## Producer Eligibility Predicate

An identity is producer-eligible if all of the following hold:

1. identity phase is `mature`
2. identity is not `penalized`
3. trajectory head is valid and current
4. ordering score remains above the minimum configured producer threshold

The current repository can enforce the first two immediately.

## Transition Logic

### `new -> not eligible`

New identities are still in accumulation mode.
They may act, but they may not shape global history.

### `probation -> still not eligible by default`

Probation identities are partially trusted for transaction behavior, but not yet trusted enough for block production.

This is a security-first default.

### `mature -> eligible`

Only after sustained compliant behavior should an identity gain producer rights.

### `penalized -> ineligible`

Penalized identities should lose producer rights immediately.

## Optional Development Override

For demos, testing, or staged rollout, the implementation may expose an override such as:

- `allow_probationary_producers=True`
- `allow_any_producer=True`

These are development or migration tools, not the recommended production rule.

## Producer Failure Consequence

If an identity attempts to produce while ineligible:

- the block should be rejected
- no producer reward should be granted
- the identity may optionally accrue an additional penalty marker

## Recommended Implementation Order

1. enforce producer phase check in `mine_block()`
2. expose producer eligibility helper
3. optionally add explicit override flags for demo and tests
4. later connect ineligibility to stronger penalty logic

## Relationship to Future Selection Logic

This gate answers:

- who is allowed to produce

It does **not** yet answer:

- if multiple mature producers exist, who should be preferred

That is the next design step after the hard gate is implemented.

## Repository Linkage

This document operationalizes:

- [docs/POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)

It should be implemented before full producer selection and before final DAG ordering.
