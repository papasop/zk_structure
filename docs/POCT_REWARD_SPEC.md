# PoCT Reward Specification v0.1

## Goal

Define the first fully explicit reward rule for PoCT, including:

- reward formula
- producer phase shares
- penalty handling
- confirmation conditions

This document turns the current reward direction into a fixed `v0.1` protocol rule.

## Core Principle

PoCT rewards should compensate:

- ordered and confirmed block production
- sustained compliant producer behavior
- long-run network maintenance

PoCT rewards should **not** compensate:

- mere block spam
- immature identities farming early rewards
- penalized identities producing unstable history

## Reward Formula

The `v0.1` reward rule is:

`actual_reward = base_emission * phase_share * confirmation_factor`

Where:

- `base_emission` depends on block height
- `phase_share` depends on producer phase
- `confirmation_factor` depends on confirmation outcome

## Base Emission

`base_emission` follows the mainnet issuance draft defined in:

- [POCT_TOKENOMICS_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TOKENOMICS_SPEC.md)

The current `v0.1` schedule is:

- blocks `0 - 999,999`: `10.0`
- blocks `1,000,000 - 1,999,999`: `5.0`
- blocks `2,000,000 - 2,999,999`: `2.5`
- blocks `3,000,000 - 3,999,999`: `1.25`
- all later blocks: `0.05`

## Producer Phase Shares

The reward share is fixed by phase in `v0.1`:

- `new`: `0.0`
- `probation`: `0.25`
- `mature`: `1.0`
- `penalized`: `0.0`

## Why Fixed Phase Shares In v0.1

The current prototype already has a continuous score model.

However, the first explicit protocol rule should be simpler and easier to audit.

So `v0.1` uses:

- fixed phase buckets for rewards
- continuous score for ordering and maturity growth

This keeps reward rules explainable while preserving behavioral legitimacy elsewhere in the protocol.

## Confirmation Factor

The confirmation factor is fixed in `v0.1`:

- unconfirmed block: `0.0`
- confirmed block: `1.0`

There is no partial reward for merely accepted or merely ordered blocks in `v0.1`.

## Reward Eligibility Rule

A block receives reward if and only if all of the following hold:

1. the block is not the genesis block
2. the block producer is not `GENESIS`
3. the block survives virtual-order conflict resolution
4. the block is in confirmed order
5. the producer phase at reward evaluation time is reward-eligible

If any of these fail, reward is `0`.

## Phase Table

### `new`

Reward share:

- `0.0`

Meaning:

- new identities may begin participating
- they do not earn block rewards yet

### `probation`

Reward share:

- `0.25`

Meaning:

- probationary identities may earn reduced rewards
- this supports growth without allowing full early extraction

### `mature`

Reward share:

- `1.0`

Meaning:

- mature identities receive the full scheduled reward budget

### `penalized`

Reward share:

- `0.0`

Meaning:

- penalized identities lose reward eligibility until their state changes under future policy rules

## Penalty Rule

Penalties affect rewards in two ways:

1. directly through phase share
2. indirectly through maturity regression and producer exclusion

The direct `v0.1` rule is:

- if phase is `penalized`, reward is zero

The indirect rule is:

- branch conflicts and rejected actions can prevent or delay reaching `mature`
- this keeps reward extraction tied to stable compliant behavior

## Branch Conflict Consequence

If an identity accumulates branch conflicts:

- it may remain stuck below `mature`
- it may fall into `penalized`
- it therefore loses access to full reward share or all reward share

So branch conflict is both:

- an ordering/trust problem
- a reward problem

## No Reward For Mere Block Count

PoCT explicitly rejects the idea that block count alone should produce reward.

That means:

- producing many low-quality blocks should not guarantee revenue
- immature identities should not bootstrap wealth just by spam
- confirmation and behavioral quality remain central

## Confirmation Rule

The reward system relies on the PoCT confirmation layer.

A block is rewardable only once it is:

- accepted
- ordered
- confirmed

In `v0.1`, the only reward-relevant final state is `confirmed`.

## Reward Timing

Rewards should be accounted logically at confirmation time, not merely at block publication time.

This means:

- block publication may create a provisional reward candidate
- accounting becomes final only after confirmation

This avoids rewarding unstable frontier blocks too early.

## Reward Recipient

In `v0.1`, the full producer reward is assigned to:

- the `producer_id` of the confirmed block

There is no mandatory split with transaction originators, guardians, or treasury in `v0.1`.

## No Treasury Routing In v0.1

The reward rule in `v0.1` does not divert emissions to:

- treasury
- foundation
- ecosystem fund
- checkpoint relayers

Those may be introduced later, but they are not part of the current fixed reward rule.

## Rounding Rule

If implementation uses integer-denominated outputs, rounding should be deterministic and conservative.

The recommended rule is:

- compute reward in protocol units
- round down to the nearest representable on-chain unit

This avoids accidental over-issuance.

## Example Rewards

### Example 1

- block height: `500,000`
- base emission: `10.0`
- phase: `new`
- confirmed: yes

Result:

- `10.0 * 0.0 * 1.0 = 0.0`

### Example 2

- block height: `1,500,000`
- base emission: `5.0`
- phase: `probation`
- confirmed: yes

Result:

- `5.0 * 0.25 * 1.0 = 1.25`

### Example 3

- block height: `2,500,000`
- base emission: `2.5`
- phase: `mature`
- confirmed: yes

Result:

- `2.5 * 1.0 * 1.0 = 2.5`

### Example 4

- block height: `4,200,000`
- base emission: `0.05`
- phase: `mature`
- confirmed: yes

Result:

- `0.05 * 1.0 * 1.0 = 0.05`

### Example 5

- block height: `2,500,000`
- base emission: `2.5`
- phase: `penalized`
- confirmed: yes

Result:

- `2.5 * 0.0 * 1.0 = 0.0`

### Example 6

- block height: `2,500,000`
- base emission: `2.5`
- phase: `mature`
- confirmed: no

Result:

- `2.5 * 1.0 * 0.0 = 0.0`

## Relation To Current Prototype

The current codebase still uses a more continuous reward-share function in the cold-start engine.

This specification now overrides that as the recommended protocol rule for future implementation alignment.

The intended migration direction is:

- keep score-based ordering
- keep score-based maturity growth
- simplify reward distribution to phase buckets

## Minimal Implementation Rule

The first code alignment should implement:

1. `reward_amount_for_block(height)`
2. `phase_share(phase)`
3. `confirmation_factor(block)`
4. `confirmed_reward_for_block = reward_amount_for_block * phase_share * confirmation_factor`

This is sufficient to make rewards deterministic and auditable.

## Future Upgrade Path

Later versions may extend reward logic with:

- treasury routing
- compliant transaction originator sharing
- dynamic checkpoint / zk prover rewards
- bounded score modifiers inside a phase

But none of those belong to `v0.1`.

## Repository Linkage

This specification extends:

- [POCT_TOKENOMICS_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_TOKENOMICS_SPEC.md)
- [POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)
- [POCT_DAG_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_DAG_SPEC.md)

It is the fixed `v0.1` reward policy for PoCT.
