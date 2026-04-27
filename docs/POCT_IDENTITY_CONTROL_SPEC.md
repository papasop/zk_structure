# PoCT Identity Control Specification v0.1

## Goal

Define how PoCT should separate:

- long-lived identity history
- day-to-day spend keys
- producer keys
- key rotation
- emergency recovery

The purpose is to preserve trajectory continuity even when a hot key must be replaced.

## Problem Statement

If PoCT binds trajectory legitimacy directly to a single address or public key, key compromise creates a protocol dilemma:

1. either the user moves to a new address and loses trajectory history
2. or the protocol allows history transfer without a strong authorization rule

The first option destroys long-term identity legitimacy.
The second option enables identity theft.

So PoCT needs an explicit identity-control layer.

## Core Principle

PoCT should treat:

- `identity`
- `action key`
- `recovery authority`

as distinct concepts.

In short:

- `identity` holds history
- `keys` perform actions
- `recovery policy` changes keys

## Identity Object

An `identity` is a chain-recognized state object.
It is not itself a single private key.

It should contain at least:

- `identity_id`
- `status`
- `trajectory_head`
- `sequence`
- `trajectory_id`
- `ordering_score`
- `policy_root`
- `active_spend_keys`
- `active_producer_keys`
- `rotation_policy`
- `recovery_policy`
- `pending_recovery`
- `created_at`
- `updated_at`

## Why Identity Should Not Be A Single Key

If PoCT introduces a dedicated `identity private key`, the system simply moves the same compromise risk one layer higher.

That would mean:

- hot key compromise is bad
- identity key compromise is catastrophic

So the recommended model is:

- no single identity master key
- identity is controlled by policy
- different actions may require different authorities

## Key Classes

The minimum recommended key classes are:

### 1. `active_spend_key`

Used for:

- ordinary transfers
- ordinary trajectory actions

This is expected to be the hottest and most replaceable key.

### 2. `active_producer_key`

Used for:

- producer-facing actions
- future block-production authorization

This may be separated from spend authority to reduce operational risk.

### 3. `recovery_keys`

Used for:

- emergency key replacement
- identity freeze
- recovery-policy updates

These keys should be colder and more carefully distributed.

## Recommended Recovery Baseline

For `v0.1`, the recommended baseline is:

- `3` recovery guardians
- `2-of-3` threshold
- explicit recovery delay

This is intentionally small enough for a first implementation while still avoiding a single recovery point of failure.

## Why `2-of-3` Instead Of Larger Low-Threshold Sets

PoCT should prefer:

- small trusted guardian sets
- explicit thresholding

over:

- very large guardian sets with very low threshold

For example, `2-of-6` or `2-of-98` usually increases attack surface faster than it improves resiliency.

## Authority Model

Identity control should be action-specific.
Not every action requires the same threshold.

### Ordinary Actions

Examples:

- transfer
- compliant trajectory continuation

Required authority:

- valid signature from an authorized `active_spend_key`

### Normal Key Rotation

Example:

- replace a hot spend key before compromise is confirmed

Required authority:

- valid signature from the currently active key being rotated

### Emergency Recovery

Example:

- old hot key is lost, compromised, or no longer trusted

Required authority:

- `2-of-3` recovery keys
- delay before finalization

### Recovery Policy Update

Example:

- replace one guardian
- move from `2-of-3` to `3-of-5` later

Required authority:

- recovery threshold approval
- delayed activation

## Binding Rule

A new key may not self-assign to an existing identity.

The only valid binding rule is:

> a `key -> identity` relationship exists only if it was authorized by the identity's current control policy.

This prevents attackers from simply asserting:

- "this new address now inherits that identity"

## Transaction Model Shift

The protocol should gradually move from:

- `sender = address/public_key`

toward:

- `sender = identity_id`
- `action_key = current authorized key`

That means trajectory continuity remains bound to the identity object, not to the current hot key.

## Recommended Action Types

PoCT should introduce protocol-visible control actions such as:

- `transfer`
- `rotate_spend_key`
- `rotate_producer_key`
- `start_recovery`
- `cancel_recovery`
- `finalize_recovery`
- `update_recovery_policy`
- `freeze_identity`

## `rotate_spend_key`

Purpose:

- normal key replacement

Required inputs:

- `identity_id`
- `old_key_id`
- `new_key`
- current trajectory references

Required authority:

- valid signature from the currently authorized old key

Effect:

- new key becomes active for spend actions
- identity history continues
- no trajectory reset occurs

## `start_recovery`

Purpose:

- open an emergency recovery flow when the old key is no longer trustworthy

Required inputs:

- `identity_id`
- proposed `new_key`
- guardian approvals meeting threshold
- recovery start timestamp

Effect:

- creates a `pending_recovery`
- does not immediately replace the active key

## `cancel_recovery`

Purpose:

- stop a malicious or mistaken recovery before it finalizes

Allowed authority options:

- currently valid active key
- stronger future veto authority if defined later

Effect:

- removes the pending recovery

## `finalize_recovery`

Purpose:

- complete emergency reassignment after the delay window has passed

Required checks:

- pending recovery exists
- guardian approvals still satisfy threshold
- delay has elapsed
- no valid cancellation exists

Effect:

- proposed new key becomes active
- identity continuity is preserved

## Recovery Delay

Recovery should not take effect immediately.

The purpose of the delay is to:

- give the real user time to notice
- allow cancellation if the old key is still controlled
- reduce damage from guardian collusion

The delay should also apply to recovery-policy changes.

## Guardian Collusion Model

PoCT should assume that a subset of guardians may collude.

So the design goal is not:

- "make collusion impossible"

The design goal is:

- raise attack cost
- minimize attack surface
- provide time to detect and respond

That is why threshold recovery should be combined with:

- a small trusted set
- delay
- on-chain visibility

## Freeze Option

An optional `freeze_identity` action may be useful in later versions.

Purpose:

- temporarily disable sensitive control changes
- reduce damage while a recovery dispute is being resolved

This is useful but not required for the first implementation.

## Interaction With Trajectory Rules

Identity control does not replace trajectory validity.
It changes which key is allowed to continue the same trajectory.

So the continuity rule becomes:

- the next action must extend the identity's current head
- and must be signed by a currently authorized key for that action type

This is the critical bridge between trajectory logic and recoverable identity logic.

## Interaction With Producer Legitimacy

Producer legitimacy should remain attached to the identity rather than to a single producer key.

That means:

- rotating a producer key should not erase maturity
- recovering a spend key should not erase ordering history

Otherwise the PoCT legitimacy model would be too fragile under operational key changes.

## Migration Guidance For Current Repository

The current repository can evolve in this order:

1. introduce `identity_id` as the long-lived sender identity
2. rename current sender-bound head commitments toward identity-bound commitments
3. add control actions for key rotation and recovery
4. keep current address-like public keys as first `action_key` instances
5. later split spend and producer authority if needed

## Minimal First Implementation

The first implementation does not need the full long-term governance system.

It only needs:

- identity object
- active spend key
- `2-of-3` recovery set
- recovery delay
- `rotate_spend_key`
- `start_recovery`
- `finalize_recovery`

That is enough to solve the key-compromise problem without overcomplicating the protocol.

## Repository Linkage

This document extends:

- [POCT_TRAJECTORY_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TRAJECTORY_SPEC.md)
- [POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)
- [POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)

It defines how identity continuity survives key replacement while remaining compatible with PoCT legality and ordering.
