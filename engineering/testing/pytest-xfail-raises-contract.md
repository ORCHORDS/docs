# pytest expected-failure exception contract

**Issue**

An unconditional xfail can accept any failure, including unrelated setup regressions, as expected.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use the `raises` parameter to constrain the expected exception type.
- Add `match` or explicit assertions where message or error code is part of the contract.
- Run with strict xfail policy so unexpected passes require review.

## Verification

1. Trigger the intended exception, a different exception, and no exception.
2. Test setup/teardown failures separately.
3. Audit xfail age and ownership.

## Gotchas

- Xfail is not a substitute for fixing flaky tests.
- Broad base exception types weaken the contract.
- An XPASS can indicate the defect is fixed.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/how-to/skipping.html#raises-parameter)
