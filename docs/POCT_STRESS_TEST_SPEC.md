# PoCT Stress Test Specification v0.1

## Goal

Define the first load and benchmark harness for PoCT under many-agent conditions.

## Required Tools

- node RPC target
- load generator
- batch agent simulator
- benchmark recorder

## Metrics

- accepted tx/s
- rejected tx/s
- block production latency
- virtual ordering latency
- confirmation latency
- L1 feed export latency

## Workloads

- compliant burst
- same-sender branch conflict burst
- parallel double-spend burst
- many-new-agent cold-start burst
