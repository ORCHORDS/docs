# pytest JUnit suite-property worker merge boundary

**Issue**

Session-level JUnit properties are not automatically safe under distributed execution and can be missing or inconsistent across workers.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Define which process owns suite-level properties.
- Merge worker metadata deterministically before publishing XML.
- Keep required test results independent of optional metadata.

## Verification

1. Run serial and distributed suites and diff XML semantics.
2. Give workers conflicting values and require deterministic rejection or merge.
3. Test worker crash and zero-test shards.

## Gotchas

- `record_testsuite_property` has xdist limitations.
- Duplicate properties may confuse consumers.
- Metadata success must not hide missing test cases.

## Official source

- [Official documentation](https://docs.pytest.org/en/stable/reference/reference.html#pytest.record_testsuite_property)
