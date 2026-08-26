# JUnit @FieldSource argument contract

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Problem

Field-backed parameterized tests can silently share mutable arguments or fail discovery when field shape and lifecycle do not match the test contract.

## When to use

Use when test arguments are naturally maintained as a named static field or supplier.

## Controls

Keep sources deterministic and immutable, name fields explicitly, avoid secrets, and validate argument counts and types.

## Implementation

Define a stable field source, copy mutable values per invocation, pin display names, and keep discovery failures fatal in CI.

## Tests

Test empty, null, mutable, inherited, overloaded, parallel, and mismatched argument sources.

## Gotchas

Source fields are normally static and their iteration order becomes part of diagnostic reproducibility.

## Official sources

- [Official documentation](https://junit.org/junit5/docs/current/user-guide/#writing-tests-parameterized-tests-sources-FieldSource)
