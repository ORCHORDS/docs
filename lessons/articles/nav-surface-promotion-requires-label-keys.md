# nav-surface-promotion-requires-label-keys

**Issue:** mobile/desktop navigation parity
**Date:** 2026-08-23
**Repo:** example-org/example-repo at e8ac9691
**Author:** the platform team
**Status:** verified-live (example.com)

## Symptom
After promoting five drawer-only destinations (Search, Creators, Invite, Mint, Roadmap) into the desktop sidebar's "More" flyout, the flyout rendered raw i18n keys (`leftSidebar.creators`, `leftSidebar.search`, …) instead of labels. The mobile drawer (different key family `nav.*`) rendered correctly, so the bug only appeared on the newly-added surface — caught by a post-deploy Playwright click-through, not by CI.

## Root cause
Two navigation surfaces resolve labels through **different key families**: the sidebar/mobile-tabs read `leftSidebar.${labelKey}` while the compact drawer reads a full `drawerLabelKey` (mostly `nav.*`). Adding a destination to a new surface without adding that surface's keys to every locale catalog makes `t()` fall back to the key string. Non-English catalogs often have **partial** key sets (missing keys fall back to English), so an English-only key addition still leaves other locales broken.

## Fix
9771451a + e8ac9691 (`apps/web/src/lib/navigationModel.ts`, `apps/web/src/messages/*.json`) — added `leftSidebar.{creators,search,invite,mint,roadmap}` to all 18 locale catalogs; regression test now asserts every sidebar/tab `labelKey` resolves in en.json.

## Verification
- **Test:** `navigationModel.test.ts > resolves every sidebar label key rendered by LeftSidebar and MobileTabBar` — passes
- **CI:** green chain at e8ac9691 (ci, gitleaks, deploy-web, deploy-functions, deploy-admin)
- **Live:** Playwright read of desktop More flyout shows "Creators", not "leftSidebar.creators"

## Gotchas
- Single canonical navigation model ≠ parity: also enforce a `findParityGaps()`-style contract (every destination reachable on every layout family) as a test, or destinations silently vanish when a surface is `display:none` at a breakpoint.
- Feed filter tabs must be `kind: "feed-filter"` children of a destination — if they leak into `getDrawerItems()`, viewport width changes their architectural status (top-level on mobile, in-page tab on desktop).
- Signed-out drawers must filter `requiresAuth === false`; re-check after any promotion.

## Related
- example-org/example-repo #1342 (adaptive navigation), #1516, #1517, #1518
