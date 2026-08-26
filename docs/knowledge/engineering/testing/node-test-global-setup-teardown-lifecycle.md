# Node.js test global setup and teardown lifecycle

**Issue:** Starting shared databases, servers, or fixtures independently in each test wastes time, while careless global state creates coupling and cleanup failures.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

Use a dedicated module selected by `--test-global-setup` that exports `globalSetup` and `globalTeardown`. Keep setup idempotent, bind ephemeral ports, and return readiness only after dependencies are usable. Record resource handles in module scope rather than global variables visible to tests. Tests must still create isolated data namespaces; global lifecycle is for infrastructure, not mutable test state.

Account for Node's failure semantics: if global setup throws, tests do not run and global teardown is not called. Setup must therefore clean partial resources before rethrowing or delegate cleanup to an external lease with expiry. Teardown should tolerate partially closed resources and preserve the original test failure.

## Verification

Force setup failure at each allocation step and prove no process, port, file, or database remains. Test normal pass, assertion failure, timeout, and termination paths. Run shards concurrently and confirm their resource identities cannot collide.

## Gotchas

- A single global resource can serialize tests or leak state between files.
- Teardown success does not prove external resources were deleted; verify independently.
- Pin the supported Node release because test-runner flags evolve.

## Official source

- [Node.js test runner documentation](https://nodejs.org/api/test.html#global-setup-and-teardown)
