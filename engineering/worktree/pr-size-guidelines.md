# pr-size-guidelines

**Issue:** Large PRs slow review cycles, bury bugs, and merge conflicts become multi-hour events
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A PR with 2,000 lines sits open for three days because reviewers keep deferring it. When it finally merges, two bugs were missed. Meanwhile three other PRs are blocked waiting for it.

## Pattern / Solution
Keep PRs small and focused. One PR = one logical change.

**Size targets:**
| Size | Lines changed | Review time target |
|------|--------------|-------------------|
| XS | < 50 | < 30 min |
| S | 50–200 | < 1 hour |
| M | 200–500 | 1–2 hours |
| L | 500–1000 | requires split or justification |
| XL | > 1000 | must be split |

**Strategies for splitting large PRs:**
1. **Feature flags:** Merge incomplete features behind a flag; iterate in multiple PRs
2. **Preparatory refactor PR:** Extract and rename in one PR; logic change in a second
3. **Vertical slices:** Ship the data layer first, then the API, then the frontend
4. **Scaffolding PR:** Add empty files/interfaces; implementation in follow-up PRs

**Exceptions (must be documented in PR description):**
- Auto-generated code (migrations, mocks, OpenAPI clients)
- Large file moves with no logic change (add `--ignore-whitespace` flag to review)
- Security patches requiring a complete module replacement

**PR description template:**
```markdown
## What
One sentence.

## Why
Link to ticket.

## How
Key implementation decisions.

## Testing
How to verify locally.

## Screenshots (if UI)
```

## Gotchas
- Lines of test code count — a 200-line feature + 800 lines of tests is still a large PR
- "It's all one feature" is not a valid reason to keep a 1,500-line PR; slice the feature
- Auto-generated files should be committed in a separate, labeled commit so reviewers can skip them

## Related
- `code-review-checklist.md`
- `definition-of-done-checklist.md`
- `pr-review-process-2026.md`
