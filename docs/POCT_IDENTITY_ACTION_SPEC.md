# PoCT Identity Action Specification v0.1

## Goal

Define the protocol-visible action model that connects:

- trajectory continuity
- identity control
- authorized action keys
- key rotation
- emergency recovery

This document turns the identity-control layer into concrete transaction semantics.

## Why This Spec Is Needed

The repository now defines:

- identity continuity
- key classes
- recovery policy

What still needs to be fixed is the action grammar:

- what fields an identity action must carry
- which authority each action type requires
- which state objects change after validation

Without that layer, the identity model remains conceptual and cannot cleanly guide implementation.

The durable state objects consumed by those actions are defined in:

- [POCT_IDENTITY_STATE_OBJECT_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_STATE_OBJECT_SPEC.md)

## Core Principle

Every PoCT action should answer three questions explicitly:

1. which `identity_id` is acting
2. which authorized key or guardian set is speaking
3. which state transition is being requested

In short:

`identity + authority + action_type + continuity = valid state transition`

## Terminology

### `identity_id`

The durable history-bearing subject whose trajectory and legitimacy persist across key rotation.

### `action_key`

A currently authorized key allowed to perform some class of actions on behalf of the identity.

### `guardian approval`

A recovery-scope signature or approval emitted by one of the registered recovery authorities.

### `action`

A protocol-level request that changes PoCT state if accepted.

## Action Families

PoCT should distinguish at least these action families:

- ordinary spend actions
- producer-control actions
- key-rotation actions
- recovery actions
- policy-governance actions

For `v0.1`, the minimum required concrete action types are:

- `transfer`
- `rotate_spend_key`
- `start_recovery`
- `cancel_recovery`
- `finalize_recovery`

## Recommended Envelope Shape

The current repository still uses a transaction object centered on:

- `sender`
- `trajectory_id`
- `prev`
- `sequence`

The recommended next-step envelope should evolve toward:

- `identity_id`
- `action_type`
- `action_key`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `identity_head_commitment`
- `payload`
- `approvals`

This may still be serialized inside the current transaction structure during migration.

## Base Fields

Every identity action should include:

- `action_id`
- `identity_id`
- `action_type`
- `action_key`
- `prev`
- `sequence`
- `epoch`
- `policy_hash`
- `delta`
- `identity_head_commitment`
- `payload`
- `approvals`
- `timestamp`

## Field Meaning

### `action_id`

Stable hash or identifier for the action object.

### `identity_id`

The long-lived identity whose trajectory this action extends.

### `action_type`

The semantic transition being requested, such as:

- `transfer`
- `rotate_spend_key`
- `start_recovery`

### `action_key`

The currently presented key intended to authorize the action.

This is not necessarily the only authority source because recovery actions may rely on guardian approvals instead.

### `prev`

Reference to the identity's latest accepted action.

### `sequence`

Monotonic identity-local sequence number.

### `policy_hash`

Commitment to the policy regime under which the action was created.

### `identity_head_commitment`

Commitment to the current accepted head of the identity at signing time.

### `payload`

Action-specific data.

### `approvals`

One or more signatures, guardian approvals, or future proof objects needed by the action type.

## Action-Specific Payloads

### 1. `transfer`

Purpose:

- move value under ordinary spend authority

Payload should include:

- `inputs`
- `outputs`
- optional transfer memo or constrained policy data

Required authority:

- valid `active_spend_key`

State effects:

- spend and create UTXOs
- advance identity head and sequence
- update rate-limit and legitimacy state

### 2. `rotate_spend_key`

Purpose:

- replace the current spend key under normal conditions

Payload should include:

- `old_key_id`
- `new_key`
- optional activation metadata

Required authority:

- valid signature from the currently authorized old spend key

State effects:

- add or activate `new_key`
- deactivate or retire `old_key_id`
- advance identity head and sequence
- preserve trajectory continuity

### 3. `start_recovery`

Purpose:

- open emergency recovery when the current spend key is untrusted or unavailable

Payload should include:

- `proposed_new_key`
- `guardian_set_id` or current recovery-policy reference
- `reason_code`
- `recovery_delay`

Required authority:

- guardian approvals satisfying threshold

State effects:

- create `pending_recovery`
- record start time
- do not yet replace the active spend key

### 4. `cancel_recovery`

Purpose:

- stop a malicious or mistaken pending recovery

Payload should include:

- `pending_recovery_id`
- optional cancellation reason

Required authority:

- currently valid active spend key

State effects:

- delete or mark canceled the pending recovery
- advance identity head and sequence

### 5. `finalize_recovery`

Purpose:

- complete delayed recovery after threshold approval and waiting period

Payload should include:

- `pending_recovery_id`
- `proposed_new_key`

Required authority:

- proof that the pending recovery exists
- guardian approvals still meet threshold or remain referenced as durable approvals
- delay has elapsed

State effects:

- replace active spend key with the proposed new key
- clear pending recovery
- advance identity head and sequence

## Approvals Model

For ordinary actions, `approvals` may contain a single action-key signature.

For recovery actions, `approvals` should support multiple guardian signatures.

The minimum recommended structure is:

- `authority_type`
- `signer_key_id`
- `signature`
- optional `signed_at`

This keeps the envelope compatible with both single-key and threshold-controlled actions.

## Validation Order

PoCT should validate identity actions in a deterministic fixed order.

Recommended order:

1. action object integrity
2. identity existence and status
3. action type recognition
4. authority eligibility for that action type
5. approval threshold or signature validity
6. trajectory continuity
7. pending-recovery constraints
8. policy validity
9. value and state validity
10. state transition application

## Step Details

### 1. Action Object Integrity

Check:

- required fields exist
- no malformed payload
- action identifier matches serialization rule

### 2. Identity Existence And Status

Check:

- `identity_id` exists unless this is a future identity-creation path
- identity is not frozen or otherwise forbidden from this action

### 3. Action Type Recognition

Check:

- `action_type` is one of the protocol-defined actions

### 4. Authority Eligibility

Check:

- spend key may authorize `transfer`
- old spend key may authorize `rotate_spend_key`
- guardians may authorize `start_recovery`

This step is about role eligibility before cryptographic verification details.

### 5. Approval Validity

Check:

- signature verifies
- each guardian is registered
- threshold is met for recovery actions

### 6. Trajectory Continuity

Check:

- `prev` equals the current head
- `sequence = current_sequence + 1`
- `identity_head_commitment` matches the expected head

### 7. Pending-Recovery Constraints

Check examples:

- `start_recovery` may be rejected if another pending recovery is already active
- `cancel_recovery` requires a pending recovery to exist
- `finalize_recovery` requires the pending recovery delay to have elapsed

### 8. Policy Validity

Check:

- `policy_hash` matches active policy expectations
- action does not violate policy-native rules

### 9. Value And State Validity

Check:

- transfer inputs exist and are owned
- outputs do not exceed inputs
- recovery payload matches the recorded pending state

### 10. State Transition Application

Apply changes only after all previous checks succeed.

## State Objects Updated By Actions

At minimum, the implementation should expect to update:

- UTXO set
- identity trajectory head
- identity sequence
- active spend key set
- pending recovery state
- legitimacy / rate-limit history

## Pending Recovery Object

The minimum recommended `pending_recovery` structure is:

- `pending_recovery_id`
- `identity_id`
- `proposed_new_key`
- `guardian_approvals`
- `started_at`
- `delay_until`
- `status`

This object should be durable and visible so peers can deterministically evaluate `finalize_recovery`.

## Identity Head Commitment

The action layer should migrate toward an identity-bound head commitment rather than a sender-key-bound commitment.

Purpose:

- survive hot key rotation
- preserve continuity semantics
- prevent competing successor actions

## Interaction With Current Transaction Model

The current repository does not need an immediate hard break.

A staged migration path is:

1. keep the existing transaction container
2. reinterpret `sender` as a temporary stand-in for `identity_id`
3. add `action_type` and `action_key`
4. rename `sender_head_commitment` toward `identity_head_commitment`
5. later split ordinary transfer payload from control-action payload

## Required Invariants

The identity action model should preserve these invariants:

- no key may self-bind to an identity
- no accepted action may skip the current identity head
- no recovery may finalize before its delay
- no ordinary transfer may execute under guardian-only authority
- no identity history reset occurs during valid key rotation

## Recommended First Implementation Scope

The first implementation only needs:

- `transfer`
- `rotate_spend_key`
- `start_recovery`
- `cancel_recovery`
- `finalize_recovery`

That is enough to test the layered identity model without prematurely expanding governance complexity.

## Repository Linkage

This specification extends:

- [POCT_IDENTITY_CONTROL_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_CONTROL_SPEC.md)
- [POCT_TRAJECTORY_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TRAJECTORY_SPEC.md)
- [POCT_STATE_TRANSITION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_STATE_TRANSITION_SPEC.md)

It is the concrete bridge from identity design to implementable ledger actions.
