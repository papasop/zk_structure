# PoCT Identity State Object Specification v0.1

## Goal

Define the concrete state objects required to support:

- durable identity continuity
- authorized action keys
- key rotation
- delayed threshold recovery
- trajectory legitimacy

This document is the state-side companion to the identity action specification.

## Why This Spec Is Needed

The repository now defines:

- identity control policy
- identity action grammar

But the current prototype state is still split primarily across:

- sender trajectory state
- cold-start identity state

That is not yet enough to represent:

- active spend keys
- active producer keys
- recovery policy
- pending recovery lifecycle

So the codebase needs a target state model before implementation migration begins.

## Design Principle

The identity state layer should separate:

- long-lived identity legitimacy
- key authorization state
- recovery governance state
- transient pending-recovery workflow state

In short:

`identity history != hot key != guardian policy != pending recovery`

## Current Repository State

The current ledger prototype mainly stores:

- `sender_states`
- `identity_states`

Where:

- `sender_states` tracks trajectory continuity and branch conflicts
- `identity_states` tracks cold-start maturity and ordering score inputs

This is a useful base, but it still assumes sender-like keys are the practical identity anchor.

## Recommended Top-Level Objects

The minimum recommended state model is:

- `IdentityState`
- `KeyAuthorizationState`
- `RecoveryPolicyState`
- `PendingRecoveryState`

These may be stored separately or nested, but their semantics should remain distinct.

## 1. `IdentityState`

`IdentityState` is the durable core object for one PoCT identity.

It should contain at least:

- `identity_id`
- `trajectory_id`
- `head_action_id`
- `sequence`
- `status`
- `branch_conflicts`
- `recent_epochs`
- `policy_root`
- `created_at`
- `updated_at`

## `IdentityState` Field Meaning

### `identity_id`

Stable long-lived identity handle.

### `trajectory_id`

Current active trajectory identifier for the identity.

### `head_action_id`

The latest accepted action in the identity trajectory.

### `sequence`

Current accepted identity-local sequence number.

### `status`

Identity status such as:

- `new`
- `probation`
- `mature`
- `penalized`
- optional future `frozen`

### `branch_conflicts`

Accumulated or current branch-conflict count relevant to legitimacy and penalties.

### `recent_epochs`

Recent accepted activity epochs used for rate-limit enforcement.

### `policy_root`

Current policy commitment root or policy version anchor for the identity.

## 2. `KeyAuthorizationState`

`KeyAuthorizationState` tracks which keys are currently allowed to speak for the identity.

It should contain at least:

- `identity_id`
- `active_spend_keys`
- `active_producer_keys`
- `retired_keys`
- `key_version`
- `last_rotation_at`

## `KeyAuthorizationState` Field Meaning

### `active_spend_keys`

Keys currently allowed to authorize ordinary transfer and trajectory actions.

For `v0.1`, this may contain exactly one active spend key.

### `active_producer_keys`

Keys currently allowed to authorize producer-facing actions.

This may initially mirror the spend key model and later diverge.

### `retired_keys`

Keys that were previously authorized but are no longer valid for future actions.

Keeping them visible helps deterministic audit and replay analysis.

### `key_version`

Monotonic version marker that advances on successful key rotation or recovery finalization.

### `last_rotation_at`

Timestamp or epoch of the most recent key change.

## 3. `RecoveryPolicyState`

`RecoveryPolicyState` defines how emergency control changes are authorized.

It should contain at least:

- `identity_id`
- `guardian_keys`
- `threshold`
- `recovery_delay`
- `policy_version`
- `updated_at`

## `RecoveryPolicyState` Field Meaning

### `guardian_keys`

The registered guardian or recovery authority keys.

For the recommended baseline, this should hold `3` guardians.

### `threshold`

Minimum number of guardian approvals required.

For the recommended baseline, this is `2`.

### `recovery_delay`

Minimum waiting period between recovery start and valid finalization.

### `policy_version`

Monotonic marker used when the guardian set or threshold changes.

## 4. `PendingRecoveryState`

`PendingRecoveryState` represents an in-flight emergency reassignment flow.

It should contain at least:

- `pending_recovery_id`
- `identity_id`
- `proposed_new_spend_key`
- `guardian_approvals`
- `started_at`
- `delay_until`
- `status`
- `reason_code`

## `PendingRecoveryState` Status Values

The minimum recommended status values are:

- `pending`
- `canceled`
- `finalized`
- optional future `expired`

## Why `PendingRecoveryState` Should Be Explicit

Recovery should not be inferred implicitly from loose recent actions.

It must be an explicit durable object because validators need deterministic answers to:

- whether recovery is active
- which new key is proposed
- when finalization becomes legal
- whether cancellation already occurred

## Cold-Start And Ordering State

The current `ColdStartState` should remain conceptually separate from key authorization.

It tracks:

- compliant transaction count
- rejected transaction count
- branch conflict impact
- ordering score inputs

This can remain a dedicated sub-object or be embedded inside a broader identity aggregate.

The important rule is:

- maturity state belongs to identity legitimacy
- not to key authorization

## Recommended Aggregate View

For implementation convenience, a repository may expose an aggregate view such as:

```text
IdentityAggregate {
  identity: IdentityState
  keys: KeyAuthorizationState
  recovery_policy: RecoveryPolicyState
  pending_recovery: PendingRecoveryState | null
  cold_start: ColdStartState
}
```

This aggregate is useful for validators even if persistence stores the pieces separately.

## State Transition Ownership

Each action type should modify only the relevant sub-objects.

### `transfer`

Updates:

- `IdentityState`
- UTXO set
- `ColdStartState`

Does not normally update:

- `RecoveryPolicyState`

### `rotate_spend_key`

Updates:

- `IdentityState`
- `KeyAuthorizationState`

Does not normally update:

- `RecoveryPolicyState`

### `start_recovery`

Updates:

- `IdentityState`
- `PendingRecoveryState`

May read:

- `RecoveryPolicyState`

### `cancel_recovery`

Updates:

- `IdentityState`
- `PendingRecoveryState`

### `finalize_recovery`

Updates:

- `IdentityState`
- `KeyAuthorizationState`
- `PendingRecoveryState`

## Invariants

The state model should preserve at least these invariants:

- one identity has at most one active head
- one identity has at most one active pending recovery
- retired keys cannot authorize new actions
- guardian approvals must reference the current recovery policy version
- key rotation does not reset identity maturity
- recovery finalization does not erase branch-conflict history

## Persistence Guidance

Persisted state should represent these objects explicitly enough to survive restart without ambiguity.

At minimum, persistence should preserve:

- identity trajectory head
- active keys
- guardian set and threshold
- pending recovery status
- cold-start legitimacy state

This is necessary for deterministic validation after reload.

## Migration From Current Prototype

The current repository can migrate in stages.

### Stage 1

Keep the existing current objects, but reinterpret them:

- `sender_states` -> provisional identity trajectory state
- `identity_states` -> cold-start legitimacy state

### Stage 2

Introduce new first-class containers:

- `key_authorizations`
- `recovery_policies`
- `pending_recoveries`

while still keeping old transaction formats during compatibility mode.

### Stage 3

Rename and consolidate:

- `SenderTrajectoryState` -> `IdentityState`
- `sender_head_commitment` -> `identity_head_commitment`
- `sender` -> `identity_id` plus explicit action key

### Stage 4

Introduce action-type-specific validation using the new state objects as the authoritative source.

## Mapping To Current Code

The current dataclass:

- `SenderTrajectoryState(sender, trajectory_id, head_txid, sequence, recent_epochs, phase, branch_conflicts)`

maps approximately to:

- `IdentityState.identity_id`
- `IdentityState.trajectory_id`
- `IdentityState.head_action_id`
- `IdentityState.sequence`
- `IdentityState.recent_epochs`
- `IdentityState.status`
- `IdentityState.branch_conflicts`

The current `ColdStartState` should continue supplying:

- phase derivation
- ordering score
- reward share

until the repository decides whether to embed or keep it standalone.

## Minimal First Implementation

The first implementation does not need the full long-term object graph.

It only needs:

- `IdentityState`
- one active spend key per identity
- one `RecoveryPolicyState`
- zero-or-one `PendingRecoveryState`

That is enough to support the first identity-controlled recovery path.

## Repository Linkage

This specification extends:

- [POCT_IDENTITY_CONTROL_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_CONTROL_SPEC.md)
- [POCT_IDENTITY_ACTION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_ACTION_SPEC.md)
- [POCT_STATE_TRANSITION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_STATE_TRANSITION_SPEC.md)

It defines the durable state target that the repository should migrate toward.
