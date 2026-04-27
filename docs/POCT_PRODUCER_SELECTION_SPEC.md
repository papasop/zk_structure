# PoCT Producer Selection Specification v0.1

## Goal

After producer gating, the next question is:

> if several eligible producers exist at the same time, which one should be preferred?

This document defines the first deterministic producer comparison rule for PoCT.

It is intentionally simple and should be used as the bridge between:

- producer eligibility
- future DAG block ordering

## Scope

This specification does **not** define full network consensus.
It defines only a deterministic producer priority policy.

That policy can later be reused by:

- linear-chain leader choice
- DAG frontier ordering
- virtual main order derivation

## Selection Inputs

Each producer comparison uses the following inputs:

- producer phase
- producer ordering score
- producer average delta
- producer branch conflict count
- proposal timestamp
- producer identity string

## Priority Order

When comparing two candidate producers, prefer in this order:

1. higher phase
2. higher ordering score
3. lower average delta
4. lower branch conflict count
5. earlier timestamp within bounded skew
6. lexical producer id as deterministic tie-break

## Phase Ranking

Use the following phase order:

- `mature`
- `probation`
- `new`
- `penalized`

In practice, producer gating should already exclude `new` and `penalized` from normal production.
Still, the selection rule remains total and deterministic if such states appear in testing or transition windows.

## Ordering Score

The producer ordering score should come from the PoCT cold-start / trajectory accumulation logic.

Current repository source:

- [structural_crypto/consensus/cold_start.py](/Users/bai/Documents/New%20project/zk_structure/structural_crypto/consensus/cold_start.py)

Interpretation:

- higher score means more trusted trajectory continuity
- score should dominate all subcriteria after phase

## Average Delta

Average delta is a quality metric.

Interpretation:

- lower delta means more stable and compliant historical behavior
- it should break ties among similar ordering scores

## Branch Conflict Count

Branch conflicts signal instability or attempted manipulation.

Interpretation:

- fewer conflicts are always better
- conflict count should reduce priority even if raw score is otherwise similar

## Timestamp Rule

Timestamp should not dominate the comparison.
It should only serve as a late tie-break after legitimacy-weighted metrics.

Recommended use:

- compare timestamps only within a bounded validity window
- if skew is too large, treat the later timestamp as lower priority or invalid depending on future network rules

For now, it is only a local deterministic ordering input.

## Final Tie-Break

If all higher-level criteria match, use lexical order on the producer identity string.

Purpose:

- deterministic
- simple
- reproducible across nodes

## Suggested Comparator

Conceptually:

1. compare phase rank
2. compare ordering score
3. compare average delta
4. compare branch conflicts
5. compare timestamp
6. compare producer id

This should yield a total ordering over candidate producers.

## Why This Fits PoCT

PoW prefers greater work.
PoS prefers greater stake.
PoCT should prefer greater **trajectory legitimacy**.

That means the comparator must follow this logic:

- maturity first
- trusted continuity second
- quality third
- deterministic tie-break last

## Recommended Coding Use

Before full DAG ordering exists, use this comparator for:

- candidate block proposer sorting
- mempool-local block assembly preference
- simulation and test harnesses

Later, reuse the same comparator inside DAG virtual-order construction.

## Relationship to Future DAG Ordering

This specification is **not** the full DAG ordering rule.

It only provides the producer-preference component.

Future DAG ordering will still need:

- parent connectivity rules
- frontier scoring
- multi-block merge policy
- virtual order derivation

But those later rules should reuse this producer comparator rather than invent a new preference system.

## Repository Linkage

This specification extends:

- [docs/POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)
- [docs/POCT_PRODUCER_GATE_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_PRODUCER_GATE_SPEC.md)

It is the recommended next input to future DAG block ordering work.
