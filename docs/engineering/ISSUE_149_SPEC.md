# TimelinePanel Specification

**Resolves:** #149

Interface lives at ``src/UI/TimelinePanel.cpp``.

## Responsibilities

- Core behaviour implied by issue #149.
- Stable public surface; no UI-framework specifics in headers.
- Layering: respects ARCHITECTURE_OVERVIEW.md boundaries.

## Threading & Errors

- Public methods safe to call from UI thread.
- Returns `bool` or `std::expected<T, Error>`; never throws across module boundaries.
- All errors logged via `Logging.h` at `warn` or higher.

## Performance Budget

- Hot-path methods: < 1 ms per call for typical inputs.
- No heap allocation on render hot path; use per-frame arena.
