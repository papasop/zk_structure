# PoCT Persistence Specification v0.1

## Goal

This document defines how the current PoCT-DAG prototype persists local L0 state.

The current implementation uses:

- JSON state export
- JSON file persistence
- CLI save/load and DAG inspection commands

The purpose is to stabilize the local prototype workflow before later migration to stronger storage backends.

## Scope

This specification covers:

- in-memory state export format
- file-based persistence
- CLI persistence workflow

It does not yet define:

- database storage
- network replication
- snapshot pruning
- cryptographic state commitments over persistence blobs

## Persistence Model

The current persistence model is full-state serialization.

That means the local node stores:

- configuration
- blocks
- frontier
- mempool
- UTXO set
- sender trajectory state
- identity maturation state

This is intentionally simple and readable.

## Exported State Components

The exported state currently contains:

### 1. `config`

- `difficulty`
- `producer_reward`
- `rate_limit_window`
- `max_txs_per_window`
- `min_tx_gap`
- `allow_probationary_producers`
- `allow_new_producers`
- `confirmation_threshold`

### 2. `blocks`

Each block contains:

- `index`
- `parents`
- `timestamp`
- `nonce`
- `difficulty`
- `producer_id`
- `producer_phase`
- `producer_ordering_score`
- `aggregate_delta`
- `trajectory_commitment`
- `virtual_order_hint`
- `transactions`
- `merkle_root`
- `block_hash`

### 3. `frontier`

The currently visible frontier block hashes.

### 4. `mempool`

All pending transactions not yet integrated into finalized block application logic.

### 5. `utxos`

The current UTXO view.

### 6. `sender_states`

Per-sender trajectory state such as:

- current trajectory id
- current head
- sequence
- recent epochs
- phase
- branch conflicts

### 7. `identity_states`

Cold-start / maturity state such as:

- compliant tx count
- rejected tx count
- average delta
- branch conflicts
- external credential score
- phase

### 8. `schema_version`

The current persistence schema version.

Current value:

- `1`

## Serialization Interface

The current code exposes:

- `export_state()`
- `export_state_json()`
- `Blockchain.from_state(...)`
- `save_state(path)`
- `load_state(path)`
- `default_state_path()`

These form the current persistence API.

## File Persistence

The current file format is a single JSON file.

Default path:

- `.poct/chain_state.json`

Writes currently use:

- temporary file write
- atomic replace into the final target path

This is intended for:

- local development
- test runs
- prototype inspection

Not yet for:

- large-scale production storage
- high-frequency node synchronization

## CLI Workflow

The current CLI supports the following persistence-adjacent commands:

- `save`
- `load`
- `persist-demo`
- `show-frontier`
- `show-dag`
- `show-virtual`
- `show-resolved`
- `show-rewards`

Typical flow:

1. build and persist a local demo chain
2. inspect frontier and DAG
3. inspect virtual and confirmed order
4. inspect resolved conflicts and confirmed rewards

## Why Persistence Matters for L0

Without persistence, the current PoCT-DAG prototype would be only a transient simulation.

Persistence is necessary to make:

- trajectory history durable
- producer maturity durable
- DAG frontier durable
- reward and confirmation state durable

That means persistence is part of making L0 operational rather than merely illustrative.

## Current Limitations

The current persistence layer is intentionally minimal.

Known limitations:

- single-file rewrite model
- no incremental append log
- no snapshot pruning
- no content-addressed persistence

The following are now present in the current prototype:

- schema version field
- atomic replace for file save

These are acceptable at the prototype stage.

## Recommended Future Upgrades

### 1. Add schema versioning

Include a top-level persistence version field so future upgrades can migrate safely.

### 2. Add atomic writes

Write to temporary file and rename into place.

### 3. Add snapshot + journal split

Separate:

- large stable state snapshot
- recent append-only event log

### 4. Add state commitment

Expose a digest over the persisted state for quick consistency checking.

### 5. Add multi-file storage or sqlite backend

Only after the JSON model becomes too slow or too large.

## Design Rule Going Forward

Any new L0 state that materially affects:

- legality
- ordering
- finality
- reward accounting

must have a defined persistence representation.

Otherwise the implementation will drift away from recoverable node behavior.

## Repository Linkage

This persistence specification sits underneath:

- [docs/POCT_L0_L1_SPEC.md](/Users/bai/Documents/New%20project/zk_structure/docs/POCT_L0_L1_SPEC.md)

It documents the current local storage model of the PoCT L0 prototype.
