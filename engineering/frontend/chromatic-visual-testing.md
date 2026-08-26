# chromatic-visual-testing

**Issue:** UI regressions go undetected until production because there is no pixel-level comparison
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A CSS change fixes one component but breaks the spacing of three others with no test catching it.

## Pattern / Solution
```yaml
# .github/workflows/chromatic.yml
- name: Publish to Chromatic
  uses: chromaui/action@latest
  with:
    projectToken: ${{ secrets.CHROMATIC_PROJECT_TOKEN }}
    exitZeroOnChanges: true
```

```bash
# Local run
npx chromatic --project-token=<token>
```

Chromatic captures screenshots of every Storybook story and diffs them against the accepted baseline. Reviewers approve or deny visual changes in the Chromatic UI.

## Gotchas
- First run establishes the baseline; all subsequent runs compare against it
- exitZeroOnChanges: true allows CI to pass when changes need review (not auto-fail)
- Use TurboSnap to only snapshot stories with changed dependencies

## Related
- `storybook-component-driven.md`
- `playwright-component-testing.md`
