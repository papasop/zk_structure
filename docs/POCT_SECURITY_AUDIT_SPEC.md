# PoCT Security Audit Specification v0.1

## Goal

Prepare the protocol for structured review before a real multi-node or zk-integrated rollout.

## Audit Preconditions

- core protocol frozen enough for review
- deterministic tests in place
- state transition rules written
- persistence schema versioned

## Threat Model Areas

- trajectory forgery
- branch conflict evasion
- producer eligibility bypass
- DAG ordering manipulation
- confirmation weight manipulation
- persistence corruption
- L1 feed / batch tampering

## Required Evidence

- invariant tests
- replay tests
- state round-trip tests
- conflict resolution examples
