# PoCT zk Backend Specification v0.1

## Goal

Define the integration point for replacing the current prototype proof logic with a real zk backend.

## Required Interface

- `prove(circuit_id, witness, public_inputs)`
- `verify(proof)`

## Initial Backend Modes

- `mock-zk`
- future real backend such as Circom/Groth16 or PLONK

## First Required Circuits

- trajectory validity
- policy validity
- rate-limit validity
- batch checkpoint binding

## Test Requirements

- deterministic mock backend tests
- proof serialization round-trip
- transaction validation through proof-carrying path
