# PoCT Node Specification v0.1

## Goal

Define the first headless multi-node architecture for PoCT testing.

## Node Responsibilities

- maintain local `L0` state
- accept transactions
- accept and produce blocks
- persist DAG state locally
- expose RPC views
- exchange gossip envelopes with peers

## Minimal Components

- `PoCTNode`
- `PeerInfo`
- `GossipEnvelope`
- RPC request/response layer

## Required Network Tests

- node startup from persisted state
- transaction gossip
- block gossip
- frontier synchronization
- confirmed order comparison across nodes

## Sync Scope

`v0.1` only requires:

- frontier summary exchange
- missing block fetch
- state reload from local snapshot

Full peer discovery and anti-entropy are deferred.
