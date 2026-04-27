# PoCT Tokenomics Specification v0.1

## Goal

Define a first-stage monetary policy for PoCT that is:

- simple enough to implement
- predictable enough to explain
- compatible with producer-based rewards
- suitable for an early `L0` prototype evolving toward a real network

## First-Stage Policy

The first-stage issuance model is:

**declining emissions plus a fixed low tail emission**

This means:

- early network stages issue more rewards
- later stages issue fewer rewards
- rewards do not fall fully to zero
- long-run issuance remains very small and stable

## Why This Model

PoCT does not rely on:

- proof of work
- stake lockup

Instead, it relies on:

- producer participation
- DAG ordering
- confirmation maintenance
- future zk proving and checkpoint infrastructure

For that reason, a strict zero-emission end state is not ideal for `v0.1`.

A small tail emission preserves long-run network incentives without forcing the system back into a high-fee model.

## Policy Summary

Stage 1 uses:

- a declining base producer reward
- a fixed minimum tail reward floor

The reward curve therefore has three properties:

1. early emissions are higher
2. mid-stage emissions decline in steps
3. late-stage emissions flatten into a very low constant tail

## Example Emission Curve

The following example is illustrative and can be tuned before mainnet:

### Epoch Range 1

- blocks `0 - 999,999`
- base reward: `10.0`

### Epoch Range 2

- blocks `1,000,000 - 1,999,999`
- base reward: `5.0`

### Epoch Range 3

- blocks `2,000,000 - 2,999,999`
- base reward: `2.5`

### Epoch Range 4

- blocks `3,000,000 - 3,999,999`
- base reward: `1.25`

### Tail Stage

- all later blocks
- fixed tail reward: `0.05`

This is only a shape example.

The exact block windows and values may be adjusted before production deployment.

## Mainnet Supply Philosophy

The intended monetary philosophy is:

- clear bounded issuance expectations
- early network bootstrapping support
- long-run minimal infrastructure subsidy

This should be communicated as:

**bounded supply growth with declining emissions and a fixed low tail**

instead of:

- unlimited inflation
- permanent high emissions
- abrupt reward collapse to zero

## Producer Reward Relation

Base issuance is not the whole reward.

Actual producer reward may later be modeled as:

`actual_reward = base_emission * producer_share * confirmation_factor`

Where:

- `base_emission` follows the curve above
- `producer_share` may depend on PoCT producer state
- `confirmation_factor` may depend on confirmation outcome

In other words:

the issuance curve defines the reward budget,
while PoCT determines how that budget is distributed.

## Fixed Tail Emission

The tail emission in `v0.1` is intentionally fixed, not dynamic.

This is recommended for the first stage because it is:

- easier to reason about
- easier to audit
- less vulnerable to manipulation
- easier to communicate externally

Dynamic tail emissions may be added in a later version after:

- multi-node behavior stabilizes
- producer metrics are harder to game
- network maintenance costs are better understood

## Testnet Policy

Testnet should not follow strict supply policy.

Testnet may continue to use:

- faucet issuance
- unrestricted or loosely restricted local minting
- simplified producer reward settings

Mainnet tokenomics should be treated separately from testnet utility issuance.

## Governance Boundary

This specification defines the **policy direction** for first-stage emissions.

It does not yet hard-code:

- exact total cap
- treasury allocation
- vesting schedules
- L1 settlement rewards
- future governance token rights

Those should be specified in a later tokenomics/governance phase.

## Recommended v0.1 Interpretation

For first implementation work, the protocol should assume:

- declining reward schedule
- fixed low tail floor
- no dynamic tail inflation

This should be the default monetary stance until a later `v0.2+` review.

## Future Upgrade Path

Later versions may extend this with:

- explicit mainnet supply ceiling
- treasury routing
- research and ecosystem allocations
- dynamic tail emission with bounded range
- L1 checkpoint / proving reward layers

But `v0.1` intentionally stays simple.

## Repository Linkage

This document complements:

- [docs/POCT_BLOCK_PRODUCER_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_BLOCK_PRODUCER_SPEC.md)
- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)

It provides the first-stage monetary policy target for future reward implementation work.
