# Node BoundedChannel async-operation misclassification

**Issue:** Experimental Node `BoundedChannel` has only synchronous start/end events. Wrapping a promise-returning operation with it loses async lifecycle and error phases that `TracingChannel` is designed to express.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use BoundedChannel only for synchronous lexical scopes; use TracingChannel for promise/callback work; register subscribers before work starts and pin the Node release.

## Verification

Resolve and reject promises after the lexical scope; verify bounded end occurs before async completion, then prove TracingChannel emits correct async/error phases.

## Gotchas

A neat using-scope does not make asynchronous work bounded. Experimental APIs and event shapes can change between Node releases.

## Official sources

- https://nodejs.org/api/diagnostics_channel.html
