# Kubernetes Service traffic-distribution policy

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Topology preferences such as PreferSameZone alter endpoint choice and may overload a locality or behave differently across cluster versions.

## When to use

Use when latency or cross-zone cost justifies a soft Service routing preference.

## Controls

Confirm feature support, retain health-based fallback, measure per-zone capacity, and keep required availability checks.

## Implementation

Declare trafficDistribution explicitly, validate EndpointSlices, canary traffic, compare zone load and failure behavior, then document rollback.

## Tests

Test missing local endpoints, zone outage, skewed capacity, terminating endpoints, mixed-version nodes, and policy removal.

## Gotchas

A preference is not a hard residency guarantee and must not replace network or compliance controls.

## Official sources

- [Official documentation](https://kubernetes.io/docs/concepts/services-networking/service/#traffic-distribution)
