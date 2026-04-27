# PoCT Cold Start Specification v0.1

## Goal

PoCT does not use `PoW` or `PoS` as the source of legitimacy.
It needs a cold-start rule that allows open entry without giving new identities immediate control.

This design uses:

- low-friction entry
- low initial influence
- trajectory-based maturation

## Core Principle

An identity may enter the network with minimal requirements, but it does **not** receive full ordering power or full reward power at birth.

Influence grows only through:

1. compliant transactions
2. low average `delta`
3. no branch conflicts
4. stable historical behavior

## Lifecycle

### 1. New

The identity can:

- register
- submit transactions
- start building trajectory history

The identity cannot:

- dominate ordering
- extract large rewards

### 2. Probation

Triggered after a minimum number of compliant transactions.

The identity can:

- receive partial ordering weight
- receive partial rewards

The identity is still rate-limited and monitored for branch conflicts.

### 3. Mature

Triggered after sustained compliant behavior and no unresolved branch conflicts.

The identity can:

- receive full ordering eligibility
- receive normal reward share

## External Bootstrap Credentials

External credentials are optional.
They improve startup quality but do not replace trajectory growth.

Examples:

- World ID or Holonym uniqueness proof
- Ethereum address ownership proof
- Sismo or Passport reputation proof
- institutional whitelist credential

External boost is capped.
It can help a new identity cross the earliest threshold, but it cannot create permanent dominance.

## Scoring

PoCT uses three internal components plus an optional external boost:

- history component
- low-delta component
- stability component
- capped external credential component

Informally:

`ordering_score = history + low_delta + stability + capped_external_boost`

The repository implementation lives in:

- [structural_crypto/consensus/cold_start.py](/Users/bai/Documents/New%20project/zk_structure/structural_crypto/consensus/cold_start.py)

## Recommended Policy

### Entry

- open registration
- zero or low external requirement
- ordering influence near zero

### Probation

- first 5 compliant transactions
- partial ordering eligibility
- low reward share

### Maturation

- after 20 compliant transactions
- no branch conflicts
- reward and ordering scale with trajectory score

## Why This Fits PoCT

`PoW` gives influence from work.
`PoS` gives influence from stake.
`PoCT` should give influence from **continuous compliant trajectory**.

That means cold start must not be:

- permissionless and full-power on day one
- fully centralized identity gating
- reward-first

It should be:

- open to join
- slow to influence
- strict on trajectory continuity

## Practical Recommendation

Use this default model:

1. let anyone join
2. give them almost no ordering power initially
3. allow small rewards only
4. grow influence from compliant history
5. use optional external zk credentials only as a capped boost
