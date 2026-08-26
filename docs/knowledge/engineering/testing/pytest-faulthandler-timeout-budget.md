# pytest faulthandler timeout budget

**Issue**

A hung test can consume the whole CI timeout without emitting thread stacks needed for diagnosis.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Set `faulthandler_timeout` below the job timeout.
- Keep dumps free of secrets and retain them on failure.
- Use per-test timeouts separately when termination is required.

## Verification

1. Hang Python and extension-backed tests.
2. Verify all thread stacks appear before job cancellation.
3. Test repeated hangs under parallel execution.

## Gotchas

- Faulthandler reports but does not terminate the test.
- Native deadlocks may provide limited Python frames.
- Very low timeouts create noise.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/how-to/failures.html#fault-handler)
