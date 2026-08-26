# PostgreSQL client-connection check interval

**Problem**

Long-running queries may continue work after a client disconnect until socket activity reveals the loss.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## When to use

Use where abandoned expensive queries materially waste capacity and the check overhead is acceptable.

## Controls

- Set `client_connection_check_interval` from query duration and overhead budgets.
- Keep statement timeouts and cancellation controls separate.
- Canary on representative platforms.

## Implementation

- Configure at appropriate scope and observe backend termination.
- Do not set aggressively without measurement.
- Monitor query cancellations and CPU.

## Tests

- Disconnect clients during CPU, IO, lock wait, and result production; measure detection.
- Test platform support.

## Gotchas

- Checks can add overhead.
- The default zero leaves checks to normal socket operations.
- It is not a query timeout.

## Official sources

- [Official documentation](https://www.postgresql.org/docs/current/runtime-config-connection.html)
