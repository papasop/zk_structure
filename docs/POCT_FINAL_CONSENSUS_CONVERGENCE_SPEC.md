# PoCT Final Consensus Convergence Specification v0.1

## Goal

Define the missing layer above:

- `accepted`
- `ordered`
- `confirmed`

so the network can also converge on:

- `finalized`

This document turns PoCT-DAG from a deterministic local ordering model into a protocol with an explicit network-level irreversible prefix.

## Why This Spec Is Needed

The current repository already defines:

- admissibility
- trajectory continuity
- producer eligibility
- deterministic virtual ordering
- confirmation scoring
- node sync and convergence summaries
- `L1` batch export from confirmed order

What is still missing is the final convergence anchor.

Today, two honest nodes can often reach the same:

- block set
- frontier
- virtual order
- confirmed order

But the repository does not yet define a certificate-backed rule for:

- which ordered prefix becomes irreversible
- how lagging nodes identify the canonical finalized prefix quickly
- how the network recovers if the recent visible DAG suffix is still moving

So the gap is not local determinism.
The gap is network-final convergence.

## Core Design Principle

PoCT should keep three distinct layers:

1. `DAG acceptance`
2. `virtual ordering`
3. `certificate-backed finalization`

In short:

`accept first -> order deterministically -> finalize a checkpointed prefix`

The finality layer should not replace the DAG.
It should seal prefixes of the already ordered DAG.

## Status Ladder

Every block should be understood as moving through five states:

1. `accepted`
2. `ordered`
3. `confirmed`
4. `locked`
5. `finalized`

### Meaning

- `accepted`
  The block is locally valid and all parents are known.
- `ordered`
  The block appears in the deterministic virtual order.
- `confirmed`
  The block has enough descendant support under the local confirmation rule.
- `locked`
  A committee certificate has selected a checkpoint containing the block's ordered prefix.
- `finalized`
  A later certificate makes that locked prefix irreversible.

`confirmed` remains a useful fast confidence signal.
`finalized` becomes the canonical convergence target.

## Final Convergence Target

Two honest nodes should be considered finally converged when all of the following hold:

1. they agree on the same `epoch_committee`
2. they agree on the same latest `finalized_checkpoint`
3. they agree on the same `finalized_prefix_digest`
4. they derive the same ordered block list up to that finalized checkpoint

After that, frontier and recent virtual suffix may still differ temporarily without breaking final convergence.

This is the key shift:

- `sync convergence` means recent visibility alignment
- `final convergence` means irreversible prefix alignment

## New Consensus Objects

The final layer introduces four new protocol objects.

### 1. Epoch Committee

A deterministic list of eligible finality voters for an epoch.

Each entry contains:

- `identity_id`
- `phase`
- `ordering_score`
- `finality_weight`
- `committee_epoch`

### 2. Checkpoint

A deterministic commitment to an ordered prefix.

Each checkpoint contains:

- `checkpoint_id`
- `epoch`
- `round`
- `anchor_block_hash`
- `finalized_parent`
- `ordered_prefix_end`
- `ordered_prefix_digest`
- `confirmed_batch_digest`
- `committee_digest`
- `config_digest`

### 3. Vote

A signed committee statement over a checkpoint.

Each vote contains:

- `epoch`
- `round`
- `vote_type`
- `checkpoint_id`
- `checkpoint_digest`
- `voter_id`
- `signature`

### 4. Certificate

An aggregate proof that a quorum of the epoch committee endorsed the checkpoint.

Each certificate contains:

- `epoch`
- `round`
- `vote_type`
- `checkpoint_id`
- `quorum_weight`
- `committee_digest`
- `signer_set`
- `aggregate_signature` or deterministic signer bundle

## Committee Formation

The finality committee should be derived from PoCT legitimacy, not external stake.

### Eligibility

Only identities in phase:

- `mature`

may join the normal finality committee.

Identities in:

- `probation`
- `new`
- `penalized`

do not vote in finality for `v0.1`.

### Weight Rule

Finality weight should be derived from the existing PoCT ordering score with normalization and caps.

Recommended shape:

- start from the producer ordering score
- clamp to a bounded interval
- normalize into epoch voting weights
- cap the maximum single-identity weight

Purpose:

- preserve PoCT's behavior-legitimacy root
- avoid turning finality into pure plutocracy
- avoid one highly mature identity dominating the committee

### Committee Snapshot Rule

The committee must be snapshotted at epoch boundaries from finalized history only.

That means:

- recent unfinalized score changes do not alter the current committee
- committee composition is stable during an epoch
- lagging nodes can reconstruct the same committee from finalized checkpoints

## Epoch And Round Model

Finality should run in deterministic epochs and rounds.

### Epoch

An epoch is a fixed finality window tied to a finalized checkpoint boundary.

A new epoch begins when:

- a configured number of finalized checkpoints has passed, or
- an explicit finalized committee-rotation checkpoint is reached

### Round

A round selects exactly one canonical checkpoint candidate for finality voting.

Rounds should advance when:

- a valid checkpoint candidate exists
- the node has the required parent checkpoint
- the pacemaker timeout for the current round expires

## Checkpoint Construction

PoCT should not vote on arbitrary raw frontier blocks.
It should vote on deterministic checkpoints extracted from virtual order.

### Checkpoint Input

A checkpoint should commit to:

- the latest finalized parent checkpoint
- a contiguous ordered suffix after that parent
- the anchor block at the end of that suffix
- the digest of the ordered block list in the suffix
- the digest of the confirmed `L1` batch induced by that prefix

### Anchor Selection

For `v0.1`, the simplest deterministic anchor rule is:

1. compute the current virtual order
2. ignore blocks already covered by the latest finalized checkpoint
3. find the highest block that is already `confirmed`
4. build the checkpoint from the contiguous ordered prefix ending at that block

This reuses the current repository's ordering model instead of inventing a second ordering path.

## Voting Pipeline

The recommended finality pipeline is a two-certificate lock-and-finalize flow.

### Step 1: Lock Vote

Committee members emit a `lock` vote for the round checkpoint only if:

- the checkpoint extends the latest finalized checkpoint
- all committed blocks are locally known
- the checkpoint digest matches the locally derived ordered prefix
- the round candidate is the highest valid local candidate under the deterministic rule

When the checkpoint collects more than `2/3` of total committee weight, it gains a:

- `Lock Certificate`

and becomes `locked`.

### Step 2: Finalize Vote

In the next round, committee members may emit a `finalize` vote for a descendant checkpoint only if:

- it extends the locked checkpoint
- it carries the parent lock certificate
- it preserves the ordered placement of the locked checkpoint prefix

When this descendant checkpoint collects more than `2/3` of total committee weight, the parent locked checkpoint becomes:

- `finalized`

This gives PoCT an irreversible prefix without requiring every recent frontier race to stop first.

## Finalization Rule

A checkpoint `C_r` becomes finalized when:

1. `C_r` has a valid `Lock Certificate`
2. a descendant checkpoint `C_r+1` extending `C_r` gains a valid `Finalize Certificate`
3. both certificates come from the same epoch committee

When that happens, the following become finalized together:

- checkpoint `C_r`
- every ordered block in its committed prefix
- every confirmed `L1` batch slice committed by its digest

## Safety Rule

Within one epoch committee, an honest voter must never sign two conflicting votes of the same type for the same round.

A checkpoint is conflicting if it:

- has the same `(epoch, round)` but a different checkpoint digest, or
- does not extend the same finalized parent as another signed candidate for that round

Violations should become explicit slash-like penalties in later versions.

For `v0.1`, the minimum rule is:

- record equivocation evidence
- mark the identity `penalized`
- remove it from the next committee snapshot

## Liveness Rule

If:

- fewer than `1/3` of committee weight is Byzantine
- honest nodes can eventually exchange messages
- honest nodes share the same sync-critical configuration

then the pacemaker must eventually drive all honest nodes to vote on the same eligible checkpoint for a later round.

The protocol therefore needs:

- deterministic round numbers
- timeout-based round advancement
- carry-forward of the highest known lock certificate

## Sync Summary Extension

The existing sync summary should be extended with finality fields.

Required new fields:

- `epoch`
- `committee_digest`
- `latest_locked_checkpoint`
- `latest_finalized_checkpoint`
- `finalized_prefix_digest`
- `finalized_height`
- `latest_lock_certificate_digest`
- `latest_finalize_certificate_digest`

This lets a peer distinguish:

- recent frontier mismatch
- missing finalized history
- committee mismatch
- true non-comparable divergence

## Fast Catch-Up Rule

Lagging nodes should sync in two stages.

### Stage 1: Finalized Prefix Catch-Up

1. fetch the latest finalized checkpoint
2. verify its certificate against the committee digest
3. fetch the committed ordered block slice if missing
4. reconstruct the finalized prefix digest

### Stage 2: Unfinalized Suffix Catch-Up

1. fetch missing frontier blocks after the finalized checkpoint
2. recompute virtual order locally
3. restore local `confirmed` and `locked` views

This keeps final recovery cheap even if the recent DAG suffix is noisy.

## Snapshot And Pruning Rule

Once a checkpoint is finalized, nodes may safely create:

- finalized state snapshots
- finalized `L1` batch checkpoints
- prunable historical indexes for pre-final frontier search

They must still preserve enough metadata to audit:

- finalized checkpoint digests
- committee snapshots
- finality certificates
- equivocation evidence

## Relation To Existing Confirmation

`confirmed` should remain in the protocol.

It still serves:

- fast wallet confidence
- candidate checkpoint eligibility
- local producer reward anticipation

But `confirmed` is not the final convergence target anymore.

The intended semantic ladder becomes:

- `confirmed` = high local confidence
- `locked` = quorum-selected candidate prefix
- `finalized` = irreversible network prefix

## Relation To L1

The finality layer should seal not only blocks, but also the exact `L1` consumption boundary.

Therefore each finalized checkpoint should commit to:

- the ordered block prefix digest
- the confirmed `L1` batch digest derived from that prefix

This gives `L1` a stable handoff:

- `confirmed` batches may be speculative
- `finalized` batches are settlement-safe

## Non-Comparable Divergence Cases

Nodes must refuse to claim final convergence if any of the following differ:

- `config_digest`
- `committee_digest`
- latest finalized checkpoint id
- finalized prefix digest
- verification result of the latest finality certificate

These are stronger divergence signals than ordinary frontier mismatch.

## Minimal RPC Additions

The current node RPC surface should be extended with:

- `get_finality_summary`
- `get_checkpoint`
- `get_certificate`
- `get_committee`
- `get_finalized_batch`

### Semantics

- `get_finality_summary`
  Returns the latest locked/finalized convergence view.
- `get_checkpoint`
  Returns a checkpoint object by id.
- `get_certificate`
  Returns the certificate for a checkpoint.
- `get_committee`
  Returns the epoch committee snapshot.
- `get_finalized_batch`
  Returns the deterministic `L1` batch for the latest finalized checkpoint or a requested finalized range.

## Recommended Persistence

Nodes should persist at least:

- checkpoint objects
- epoch committee snapshots
- lock certificates
- finalize certificates
- finalized prefix metadata
- finalized `L1` batch digests

Without this, crash recovery may recreate the accepted DAG but still lose finality knowledge.

## Recommended Implementation Order

### Phase 1: Finality Data Model

Add explicit models for:

- `Checkpoint`
- `Vote`
- `Certificate`
- `CommitteeSnapshot`
- `FinalitySummary`

### Phase 2: Deterministic Checkpoint Builder

Implement:

- ordered-prefix digesting
- finalized-parent tracking
- confirmed-to-checkpoint extraction

### Phase 3: Finality Engine

Implement:

- round state
- lock voting
- finalize voting
- certificate verification
- committee snapshot validation

### Phase 4: Finality-Aware Sync

Extend node sync to:

- compare finality summaries
- fast-sync finalized checkpoints first
- then reconcile the recent DAG suffix

### Phase 5: Finalized L1 Handoff

Export:

- finalized batch digest
- finalized batch range
- checkpoint-linked settlement records

## How This Fits The Current Repository

This design intentionally preserves the current repository structure.

It does not replace:

- trajectory legality
- producer scoring
- virtual ordering
- confirmation scoring
- `L1` batch export

It adds the missing irreversible seal above them.

So the full ladder becomes:

- `PoCT legality`
- `PoCT DAG ordering`
- `PoCT confirmation`
- `PoCT checkpoint lock`
- `PoCT final convergence`

That is the clean path from today's prototype to a real network consensus endpoint.
