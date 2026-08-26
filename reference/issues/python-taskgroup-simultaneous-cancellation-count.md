# Python TaskGroup simultaneous cancellation count

**Issue:** Before Python 3.13, a TaskGroup handling a child failure at the same time its parent was cancelled could confuse the group’s internal wake-up cancellation with the external cancellation and fail to preserve the parent task’s cancellation count. Code tested only on a single cancellation path can then behave differently across Python versions.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Pin and record the Python minor version for services whose shutdown or timeout logic depends on structured cancellation.
- Use `asyncio.TaskGroup` for related subtasks, but treat cancellation and child exceptions as independent signals.
- Put cleanup in `try/finally`, keep it bounded, and normally re-raise `CancelledError` after cleanup.
- Do not swallow `CancelledError` or call `uncancel()` casually; TaskGroup and `asyncio.timeout()` use cancellation internally.
- Avoid application correctness that depends on a cancellation count being exactly one. If repeated cancel requests are meaningful, specify and test that policy.
- Log task state, `cancelling()` count, child exception group, and external shutdown source without treating internal implementation details as stable business events.

## Implementation and tests

Create a parent task containing nested TaskGroups. Arrange for an inner child to raise a non-cancellation exception while another task calls `parent.cancel()` in the same event-loop window. Assert the inner group processes its exception, the outer group receives cancellation, the next await observes cancellation, and the parent’s `cancelling()` count is preserved on Python 3.13 and later.

Repeat with one and multiple external cancel calls, nested simultaneous child failures, timeout cancellation, cleanup that awaits, and cleanup that raises. Run the test matrix on every supported Python minor release; make intentional version differences explicit.

## Gotchas

TaskGroup cancels siblings after the first non-`CancelledError` child failure and later raises an `ExceptionGroup` or `BaseExceptionGroup` as appropriate. Its internal cancellation is used to wake `__aexit__()`; it must not consume an unrelated external cancellation. Python 3.13 changed simultaneous cancellation handling and count preservation.

Cancellation is cooperative. A coroutine that never reaches an await point, blocks the event loop, or suppresses cancellation can still delay shutdown.

## Official sources

- [Python 3.14: Coroutines and tasks—Task groups](https://docs.python.org/3.14/library/asyncio-task.html#task-groups)
- [Python 3.14: Task cancellation](https://docs.python.org/3.14/library/asyncio-task.html#task-cancellation)
