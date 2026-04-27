# PoCT Trajectory Specification v0.1

## Goal

PoCT requires more than transaction validity.
It requires that each accepted action belongs to a continuous, identity-bound, policy-constrained trajectory.

For `v0.1`, the current codebase still models sender continuity mostly through sender-like address keys.
The long-term design direction is to bind trajectory continuity to a durable `identity_id` whose authorized action keys may rotate over time.

This document defines:

- the minimum trajectory fields for each transaction
- the state machine for identity progression
- the definition of branch conflicts
- the connection between trajectory legitimacy and later DAG ordering

## Core Definition

A transaction is **trajectory-legitimate** if and only if all of the following hold:

1. signature validity
2. policy validity
3. continuity validity
4. uniqueness validity
5. rate-limit validity

This means PoCT legitimacy is not single-shot.
It is historical and stateful.

## Required Transaction Fields

Each transaction should include the following additional fields beyond ordinary UTXO fields:

- `trajectory_id`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `delta`
- `sender_head_commitment`

In the current prototype, `sender` is still close to an address-like public key.
In the recommended layered design, this should evolve toward:

- `sender = identity_id`
- separate authorized action key metadata and signatures

### Field Meaning

#### `trajectory_id`

A stable identifier for the sender's active compliant trajectory.

Purpose:

- binds a sequence of actions into one history
- distinguishes a mature history from a restarted one

#### `prev`

Reference to the sender's immediately previous accepted transaction in that trajectory.

Purpose:

- enforces local continuity
- prevents unconstrained replay or detached actions

#### `sequence`

The sender-local sequence number.

Purpose:

- gives a monotonic index for the sender's trajectory
- helps detect branch conflicts and skipped states

#### `epoch`

A bounded-time indicator used for rate limits and freshness.

Purpose:

- prevents stale replay
- enables window-based policy checks

#### `policy_hash`

Commitment to the policy active when the transaction was signed.

Purpose:

- ensures policy continuity is visible
- allows policy upgrade detection instead of silent drift

#### `delta`

The transaction's residual or deviation score under the structure policy.

Purpose:

- measures local compliance quality
- contributes to ordering and maturity score

#### `sender_head_commitment`

Commitment to the sender's current local trajectory head at signing time.

Purpose:

- helps prevent hidden parallel heads
- makes state transitions more explicit to validators

In a later identity-layered version, this should become an identity-bound head commitment rather than a commitment to a single long-lived hot key.

## Genesis Rule for a Trajectory

A new trajectory may begin only if:

- the sender has no current active trajectory
- or the prior trajectory is explicitly closed or penalized

The first transaction in a trajectory uses:

- `prev = null`
- `sequence = 0`

This avoids silent trajectory resets.

## Continuity Validity

A transaction is continuity-valid if:

- `prev` matches the unique latest accepted transaction of the sender
- `sequence = previous.sequence + 1`
- `trajectory_id` matches the sender's active trajectory
- `epoch` is not stale under the current time policy

If any of these fail, the transaction is rejected before ordering.

## Uniqueness Validity

For an identity, there may be only one accepted next action after a given head.

That means:

- one active identity
- one active trajectory
- one next valid successor per head

This is the rule that makes PoCT resistant to parallel self-forking.

## Branch Conflict Definition

A branch conflict exists when any of the following occur:

### Type A: Same `prev`, different transaction

Two distinct transactions from the same identity reference the same `prev`.

Meaning:

- the sender is trying to create two competing futures from one head

### Type B: Same `(sender, sequence)`, different transaction

Two distinct transactions claim the same identity sequence position.

Meaning:

- the sender is trying to occupy one timeline slot with multiple actions

### Type C: Skipped predecessor

A transaction claims a later sequence without extending the sender's current accepted head.

Meaning:

- the sender attempts discontinuous history injection

### Type D: Hidden trajectory reset

The identity introduces a fresh `trajectory_id` without a valid closure or penalty transition.

Meaning:

- the sender attempts to discard bad history without protocol acknowledgment

## Penalty Meaning

A branch conflict should:

- reject the conflicting transaction
- increment sender conflict counters
- reduce ordering score
- delay or revoke maturity

Repeated branch conflicts may move the identity into a `penalized` state.

## Identity State Machine

Each identity belongs to one state:

- `new`
- `probation`
- `mature`
- `penalized`

### `new`

Initial state.

Properties:

- may submit transactions
- low ordering influence
- low reward eligibility

Transition out:

- enough compliant transactions with no serious conflicts

### `probation`

Intermediate growth state.

Properties:

- partial ordering eligibility
- partial reward eligibility
- tighter monitoring on continuity and rate limits

Transition out:

- sustained compliant history leads to `mature`
- conflicts or repeated rejections may push back or trigger `penalized`

### `mature`

Stable compliant identity.

Properties:

- full ordering eligibility
- normal reward participation
- strongest trajectory influence

Transition out:

- major conflicts or repeated violations may trigger `penalized`

### `penalized`

Conflict or abuse state.

Properties:

- reduced or zero ordering influence
- reduced reward eligibility
- may require explicit recovery period or trajectory closure

## Key Rotation Compatibility

Trajectory continuity should survive key rotation.

That means:

- changing the active spend key should not create a fresh trajectory by default
- changing the producer key should not erase maturity
- recovery should continue the same identity history once finalized

See:

- [POCT_IDENTITY_CONTROL_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_CONTROL_SPEC.md)

## Suggested Transition Triggers

### `new -> probation`

- minimum number of compliant transactions
- no unresolved branch conflict

### `probation -> mature`

- higher compliant transaction threshold
- low average delta
- no branch conflict within recent window

### `probation -> penalized`

- repeated conflict attempts
- repeated rate-limit violations

### `mature -> penalized`

- severe branch conflict
- hidden reset attempt
- repeated continuity or policy abuse

## Rate-Limit Validity

Trajectory legitimacy also depends on time-local discipline.

Each identity should satisfy configurable constraints such as:

- max transactions per window
- minimum inter-transaction gap
- max cumulative amount per window

If a transaction exceeds rate policy, it is not trajectory-legitimate even if its signature and delta are locally valid.

## Policy Continuity

`policy_hash` exists to prevent silent policy mutation.

Allowed policy changes should follow one of two models:

1. immutable policy per trajectory
2. explicit policy-upgrade transition transaction

The second model is more flexible, but the upgrade transaction must itself be trajectory-valid and visible to validators.

## Validator Responsibilities

For each incoming transaction, the validator should:

1. verify signature
2. verify policy proof and `delta`
3. load sender's current trajectory head
4. check `prev`
5. check `sequence`
6. check `trajectory_id`
7. check `epoch` freshness
8. check rate-limit window
9. reject any branch conflict
10. update sender state if accepted

## Why This Matters for PoCT-DAG

The DAG layer should order only transactions and blocks that are already trajectory-legitimate.

This creates a strict layering:

- trajectory legitimacy decides admissibility
- DAG ordering decides final sequence among admissible actions

That is the main architectural difference from systems where consensus alone decides what history is acceptable.

## Minimal Implementation Order

Recommended coding order:

1. add trajectory fields to transaction model
2. track sender-local head state
3. enforce `prev` and `sequence`
4. detect branch conflicts
5. connect state transitions to the cold-start engine
6. only then introduce full DAG block ordering

## Repository Linkage

This specification extends:

- [docs/POCT_COLD_START.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_COLD_START.md)
- [docs/POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)

It is the next concrete protocol layer that should be implemented in code.
