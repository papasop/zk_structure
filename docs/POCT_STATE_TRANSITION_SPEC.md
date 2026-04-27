# PoCT State Transition Specification v0.1

## Goal

Define the deterministic state transition layer that all nodes and future audits rely on.

## State Domains

- UTXO set
- identity trajectory state
- identity cold-start state
- identity key authorization state
- pending recovery state
- DAG block set
- frontier

## Transition Order

1. validate action integrity
2. validate identity authority
3. validate trajectory rules
4. validate producer eligibility
5. apply accepted state transition
6. accept block
7. resolve virtual conflicts
8. compute confirmation
9. derive confirmed rewards
10. export confirmed L1 feed

## Required Invariants

- no accepted spend without owned input
- no accepted identity sequence duplication in resolved order
- no unauthorized key rotation
- no recovery finalization before delay expiry
- no confirmed reward without confirmation
- persistence round-trip preserves confirmed order

See:

- [POCT_IDENTITY_ACTION_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_IDENTITY_ACTION_SPEC.md)
