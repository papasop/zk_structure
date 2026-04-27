# PoCT State Transition Specification v0.1

## Goal

Define the deterministic state transition layer that all nodes and future audits rely on.

## State Domains

- UTXO set
- sender trajectory state
- identity cold-start state
- DAG block set
- frontier

## Transition Order

1. validate transaction
2. validate trajectory rules
3. validate producer eligibility
4. accept block
5. resolve virtual conflicts
6. compute confirmation
7. derive confirmed rewards
8. export confirmed L1 feed

## Required Invariants

- no accepted spend without owned input
- no accepted sender sequence duplication in resolved order
- no confirmed reward without confirmation
- persistence round-trip preserves confirmed order
