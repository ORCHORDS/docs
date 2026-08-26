# Branch coverage and intentional partial branches

**Issue:** Line coverage can mark a conditional line covered even when one decision path never executes.

**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Guidance

Branch coverage records whether each possible transition from a line was taken. Use it to find missing decisions, then review intentional partial branches individually rather than globally suppressing them.

## Controls and verification

- Pin the coverage tool and configuration.
- Combine branch thresholds with meaningful tests, not threshold gaming.
- Exclude generated or unreachable branches only with narrow documented markers.
- Merge parallel coverage data only from compatible source revisions and paths.
- Test both sides of security and error-handling decisions.
- Inspect reports for new partial branches during review.

## Sources

- [coverage.py: Branch coverage](https://coverage.readthedocs.io/en/latest/branch.html)
- [coverage.py: Managing processes](https://coverage.readthedocs.io/en/latest/subprocess.html)
