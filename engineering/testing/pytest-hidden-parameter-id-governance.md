# pytest hidden parameter-ID governance

**Issue**

Hiding a parameter set from a pytest node ID can improve readability, but it can also make selection and failure identity ambiguous.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Use `pytest.HIDDEN_PARAM` at most once per parametrization and only where the remaining ID is unique.
- Keep security, protocol, and regression cases explicitly named.
- Do not build CI sharding or quarantine keys from unstable display IDs alone.
- Pin pytest and review collected node IDs as an interface.

## Verification

1. Collect tests and assert node IDs are unique and stable.
2. Try hiding two cases and require collection failure.
3. Run exact-node selection and reruns for the hidden case.

## Gotchas

- The hidden case still executes.
- Only one hidden parameter set is permitted because IDs must remain unique.
- Plugin-generated IDs can change the final name.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#pytest.HIDDEN_PARAM)
