# cypress-vs-playwright

**Issue:** Choosing between Cypress and Playwright for e2e testing
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Teams debate Cypress vs Playwright. The choice affects test speed, cross-browser support, and CI costs.

## Pattern / Solution
| Factor | Cypress | Playwright |
|---|---|---|
| Browser support | Chrome, Firefox, Edge (no Safari) | Chrome, Firefox, Safari, Edge |
| Language | JS/TS only | JS/TS, Python, Java, C# |
| Parallelism | Paid feature (Cypress Cloud) | Free, built-in |
| Network mock | `cy.intercept` | `page.route` |
| Component testing | Yes (experimental) | Via `@playwright/test` |
| Speed | Slower in CI | Faster in CI |
| Debugging | Time-travel debugger | Trace viewer |
| Community | Large, older | Growing, newer |

Choose Playwright for: new projects, multi-browser requirements, free parallelism, Python/Java teams.
Choose Cypress for: existing Cypress investment, component testing with Cypress, team familiarity.

## Gotchas
- Cypress runs in the same browser process — different security model
- Playwright uses separate process per worker — truly parallel
- Migrating from Cypress to Playwright is significant work

## Related
- `playwright-setup.md`
- `end-to-end-test-strategy.md`
