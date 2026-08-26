# Python eager task factory synchronous-start ordering

**Issue:** With `asyncio.eager_task_factory`, coroutine code begins synchronously during Task construction and is scheduled on the event loop only if it blocks. A coroutine that returns or raises before its first blocking await may never enter the event-loop queue, changing ordering, exception timing, reentrancy, and instrumentation assumptions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Treat eager execution as a semantic change, not a transparent performance switch.
- Benchmark a measured cache-hit or synchronously completing workload before enabling it.
- Prefer an explicit, scoped `eager_start` choice where the supported Python API permits it over replacing the task factory for an entire shared loop.
- Keep code before the first blocking await short, non-blocking, and safe to run during the caller’s task-creation expression.
- Do not depend on “create task, then mutate state” ordering; pass complete immutable inputs before creation.
- Register tracing, task bookkeeping, ownership, and result handling in a way that also covers tasks already completed at return.
- Keep strong task references for scheduled background work and retrieve exceptions on every path.
- Pin Python minor versions and test libraries that install or assume their own loop task factory.

## Implementation and tests

Use fixtures that return synchronously, raise synchronously, block at the first await, perform a visible side effect before awaiting, recursively create a task, and hit or miss a memoization cache. Compare default scheduling with the eager factory and, on Python 3.14, explicit `eager_start` choices.

Assert ordering of caller statements, coroutine side effects, callbacks, exception observation, context variables, locks, metrics, and cancellation. Test TaskGroup creation, shutdown, and a library that expects task code to start on a later loop turn. Benchmark both hit-heavy and I/O-heavy workloads; reject a rollout with no material benefit.

## Gotchas

A synchronously finished eager task is still a Task result, but it was never scheduled for later event-loop execution. Task creation can now run user code and raise-visible failure effects before the caller reaches its next statement. If the coroutine blocks, execution resumes through ordinary scheduling.

The eager task factory was added in Python 3.12. Python 3.14 passes `eager_start` through high-level creation APIs; confirm the exact API and loop implementation used.

## Official sources

- [Python 3.14: Eager task factory](https://docs.python.org/3.14/library/asyncio-task.html#eager-task-factory)
- [Python 3.14: Creating tasks](https://docs.python.org/3.14/library/asyncio-task.html#creating-tasks)
