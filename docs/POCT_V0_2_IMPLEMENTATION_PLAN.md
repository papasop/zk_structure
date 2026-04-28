# PoCT v0.2 Implementation Plan

This document tracks the next implementation phase required to turn the current identity layer into a true protocol root for ordering, recovery, and producer legitimacy.

## Milestone

`v0.2 Identity-Rooted Consensus`

Goal:

- move `IDen` from an attached identity layer to a true consensus root
- separate identity legality from value execution
- complete recovery-state durability
- separate producer authority from spend authority
- make DAG ordering explicitly identity-aware

## Working Checklist

- [ ] Issue 1: split identity actions from value-transfer execution
- [ ] Issue 2: replace sender-centric indexing with identity-first indexing
- [ ] Issue 3: separate producer authority from spend authority
- [ ] Issue 4: introduce explicit guardian approval objects for recovery flows
- [ ] Issue 5: integrate identity legitimacy directly into DAG conflict and ordering rules
- [ ] Issue 6: version and migrate persisted identity-first state
- [ ] Issue 7: add end-to-end identity `v0.2` tests

## Recommended Implementation Order

1. separate identity actions from value transfer execution
2. promote `identity_id` to the primary ledger subject
3. split producer keys from spend keys
4. formalize recovery approvals as durable proof objects
5. integrate identity legitimacy directly into DAG conflict and ordering rules
6. version and migrate persisted identity-first state
7. add an end-to-end identity `v0.2` test suite

## Issue 1

**Title**

`v0.2: split IdentityAction from value-transfer execution`

**Goal**

Separate identity legality from UTXO or value movement so `transfer` no longer mixes identity continuity and value-state mutation in one implicit shape.

**Scope**

- [ ] define a dedicated `IdentityAction`
- [ ] define a dedicated `ValueTransfer`
- [ ] define a container or binding layer that ties the two together
- [ ] make validation order explicit: authority -> trajectory continuity -> value and state validity

**Acceptance Criteria**

- [ ] `transfer` is no longer only a semantic label over the legacy transaction shape
- [ ] identity actions can exist without requiring UTXO inputs and outputs
- [ ] value transfer can be bound to an identity action explicitly
- [ ] existing blockchain tests continue to pass
- [ ] new layered transaction tests are added

**Suggested Labels**

- `v0.2`
- `identity`
- `ledger`
- `architecture`

## Issue 2

**Title**

`v0.2: replace sender-centric indexing with identity-first indexing`

**Goal**

Complete the migration from `sender` to `identity_id + action_key` as the primary ledger model.

**Scope**

- [ ] migrate `sender_states` toward identity-first state containers
- [ ] migrate `sender_head_commitment` toward `identity_head_commitment`
- [ ] make trajectory continuity identity-local rather than sender-local
- [ ] remove or minimize compatibility-only sender-centric code paths

**Acceptance Criteria**

- [ ] ledger state uses `identity_id` as the main subject key
- [ ] `sender` is treated as a presented action key, not the long-lived subject
- [ ] continuity, branch conflict detection, and rate limits are identity-based
- [ ] state export and load remain compatible

**Suggested Labels**

- `v0.2`
- `identity`
- `refactor`
- `consensus`

## Issue 3

**Title**

`v0.2: separate producer authority from spend authority`

**Goal**

Turn `active_producer_keys` into a real independent authority class so producer legitimacy survives spend-key lifecycle changes.

**Scope**

- [ ] add `rotate_producer_key`
- [ ] add producer-only authorization checks
- [ ] ensure spend-key rotation does not reset producer legitimacy
- [ ] ensure producer-key rotation does not affect spend continuity
- [ ] update state transition logic and validation

**Acceptance Criteria**

- [ ] `active_producer_keys` has an independent lifecycle
- [ ] producer block authorization is checked against producer keys
- [ ] spend-key compromise and producer continuity are separable
- [ ] tests cover separated producer and spend key flows

**Suggested Labels**

- `v0.2`
- `identity`
- `producer`
- `security`

## Issue 4

**Title**

`v0.2: introduce explicit guardian approval objects for recovery flows`

**Goal**

Replace loose recovery payload validation with stable proof objects for guardian approvals.

**Scope**

- [ ] define a guardian approval schema
- [ ] include `guardian_key_id`
- [ ] include signed payload digest
- [ ] include `policy_version`
- [ ] include `signed_at`
- [ ] optionally include quorum or aggregate digest
- [ ] update `start_recovery` and `finalize_recovery` validation to use approval objects

**Acceptance Criteria**

- [ ] recovery approvals have stable serialization
- [ ] pending recovery persists structured proof objects
- [ ] replay validation can deterministically verify threshold approval
- [ ] tests cover missing approvals, wrong version, and insufficient threshold

**Suggested Labels**

- `v0.2`
- `identity`
- `recovery`
- `security`

## Issue 5

**Title**

`v0.2: integrate identity legitimacy directly into DAG conflict and ordering rules`

**Goal**

Make DAG ordering explicitly identity-aware instead of using identity score only as an indirect producer-weight input.

**Scope**

- [ ] add explicit penalties for same-identity conflicting blocks
- [ ] define producer self-conflict evidence
- [ ] let `penalized` and `pending_recovery` affect producer eligibility
- [ ] add identity-aware conflict handling to virtual ordering
- [ ] update block weight and ordering logic accordingly

**Acceptance Criteria**

- [ ] identity conflict affects block acceptance or ordering
- [ ] producer self-conflict is recorded and feeds legitimacy
- [ ] recovery-pending identities cannot behave like normal producers
- [ ] tests cover parallel identity conflict behavior

**Suggested Labels**

- `v0.2`
- `dag`
- `consensus`
- `identity`

## Issue 6

**Title**

`v0.2: version and migrate persisted identity-first state`

**Goal**

Give the identity-first state model a stable persistence and migration story.

**Scope**

- [ ] bump schema version
- [ ] add migration paths for older saved states
- [ ] persist `pending_recovery`
- [ ] persist `key_version`
- [ ] persist `policy_version`
- [ ] preserve compatibility for CLI save and load flows

**Acceptance Criteria**

- [ ] old state files can migrate into the newer schema
- [ ] roundtrip persistence preserves identity and recovery state
- [ ] migration is covered by dedicated tests
- [ ] CLI `save` and `load` remain functional

**Suggested Labels**

- `v0.2`
- `persistence`
- `migration`
- `identity`

## Issue 7

**Title**

`v0.2: add end-to-end identity state machine and consensus tests`

**Goal**

Build a dedicated test suite for the next identity-rooted implementation phase.

**Scope**

- [ ] rotate spend key, then continue transfer
- [ ] start recovery, then reject early finalize
- [ ] finalize recovery, then reject old key
- [ ] separate producer key and spend key
- [ ] let identity legitimacy affect producer ordering
- [ ] add identity-aware DAG conflict tests

**Acceptance Criteria**

- [ ] there is a dedicated identity `v0.2` integration suite
- [ ] the suite covers both success and failure paths
- [ ] blockchain, node, CLI, and persistence each include at least one identity-first integration flow
- [ ] the test suite runs through `unittest`

**Suggested Labels**

- `v0.2`
- `tests`
- `identity`
- `consensus`
