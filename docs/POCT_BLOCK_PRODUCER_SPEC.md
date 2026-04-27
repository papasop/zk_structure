# PoCT Block Producer Specification v0.1 (Model A)

## Goal

This document defines the first producer model for PoCT.

Model A is the **single-layer producer model**:

- all participants may submit transactions
- only sufficiently mature identities should meaningfully influence block production
- ordering power grows from compliant trajectory history, not from `PoW` work or `PoS` stake

This is the recommended implementation path for the current repository.

## Why Model A First

PoCT is still in the stage where:

- trajectory legitimacy is being implemented
- DAG ordering is not yet fully coded
- reward and producer penalties are not yet fully integrated

A single-layer producer model is the simplest bridge from the current ledger to a future PoCT-DAG.

## Producer Definition

A **block producer** is an identity that:

1. collects admissible transactions
2. packages them into a candidate block
3. publishes the block into the ledger or future DAG

Under Model A, the producer is still an ordinary network identity.
There is no separate consensus committee layer yet.

## Participation Tiers

Each identity belongs to one of these tiers:

- `new`
- `probation`
- `mature`
- `penalized`

### `new`

Capabilities:

- may submit transactions
- may begin accumulating trajectory history

Restrictions:

- should not receive meaningful producer priority
- should not dominate ordering
- should receive little or no producer reward

### `probation`

Capabilities:

- may build candidate blocks
- may participate with low producer weight

Restrictions:

- lower priority than mature identities
- reduced reward share
- stronger scrutiny for conflicts and rate abuse

### `mature`

Capabilities:

- full producer eligibility
- normal producer priority
- full reward eligibility

Restrictions:

- must maintain low conflict behavior
- may still be downgraded if the trajectory becomes unstable

### `penalized`

Capabilities:

- may still submit transactions if not fully banned

Restrictions:

- should not receive normal producer priority
- may be excluded from producer selection entirely
- should receive sharply reduced or zero producer rewards

## Producer Eligibility Rule

The recommended default rule is:

- `new`: cannot meaningfully produce blocks
- `probation`: may produce low-priority candidate blocks
- `mature`: may produce normal-priority blocks
- `penalized`: excluded or heavily deprioritized

This keeps open participation at the transaction level while limiting consensus influence.

## Producer Score

Producer selection should not be binary only.
It should be weighted by a producer score derived from:

1. identity phase
2. compliant transaction count
3. average `delta`
4. branch conflict count
5. rejection rate
6. optional capped external bootstrap evidence

The current repository already has a first scoring basis in:

- [structural_crypto/consensus/cold_start.py](/Users/bai/Documents/New%20project/zk_structure/structural_crypto/consensus/cold_start.py)

## Recommended Producer Priority

When multiple candidate producers are visible, prefer:

1. `mature` over `probation`
2. higher ordering score
3. lower recent aggregate `delta`
4. lower conflict history
5. earlier valid timestamp
6. deterministic lexical tie-break

This gives a practical producer policy before full DAG ordering is implemented.

## Producer Responsibilities

A Model A producer must:

1. include only trajectory-legitimate transactions
2. reject branch-conflicted transactions
3. respect sender rate limits
4. publish correct parent references
5. avoid self-conflicting producer behavior

If the producer publishes blocks that include invalid trajectory transitions, it should lose producer standing.

## Producer Self-Conflict

A producer commits a producer-level conflict if it:

- emits competing blocks from the same intended producer head without protocol justification
- repeatedly includes invalid branch-conflicted transactions
- attempts hidden reordering of its own published history

Producer conflicts should be penalized more heavily than ordinary user mistakes because they directly affect public ordering.

## Reward Rule

Producer rewards should be gated by maturity and ordering status.

Recommended rule:

- reward only blocks that survive ordering
- `new`: zero or negligible producer reward
- `probation`: reduced reward share
- `mature`: normal reward share
- `penalized`: slashed or zero reward

This prevents large numbers of AI agents from farming producer rewards immediately after joining.

The fixed `v0.1` reward formula and phase-share table are defined in:

- [POCT_REWARD_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_REWARD_SPEC.md)

## Why This Fits Large AI-Agent Systems

Model A is designed for a world where many AI agents may exist.

The key separation is:

- many identities may act
- only mature, stable identities should strongly shape global history

That prevents raw agent count from becoming raw consensus power.

## Relationship to DAG Ordering

Model A does not yet create a separate ordering layer.
Instead:

- the same identity space submits transactions
- mature identities gradually gain producer influence
- future DAG ordering will use those producer scores when many blocks appear in parallel

So Model A is the direct precursor to PoCT-DAG.

## Relationship to Future Model B / L0-L1

Model A is not the final architecture if the system later evolves into:

- a dedicated ordering layer
- a separate execution layer
- an L0 / L1 split

In that future:

- Model A becomes the prototype
- Model B becomes the separated architecture

For now, Model A is the correct implementation path because it matches the current codebase.

## Recommended Coding Order

1. expose producer eligibility from sender phase
2. compute producer ordering score from current trajectory state
3. gate block production by phase
4. record producer conflict penalties
5. connect producer rewards to ordered blocks
6. later upgrade block structure into multi-parent DAG blocks

## Repository Linkage

This specification builds on:

- [docs/POCT_COLD_START.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_COLD_START.md)
- [docs/POCT_TRAJECTORY_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TRAJECTORY_SPEC.md)
- [docs/POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)

It defines the current producer model that should be implemented before the full DAG ordering layer.
