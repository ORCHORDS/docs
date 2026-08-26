# flat-dotted-vs-nested-keys

**Issue:** Some i18n keys in `en.json` are flat-dotted (literal key with dots) vs nested (object tree)
**Date:** 2026-08-09
**Repo:** <your-org>/<your-repo> at main
**Author:** the platform team
**Status:** fixed (PR #i18n-getnested)

## Symptom
You write a component with `t("privacy.s1Title")`. The output is the
raw string `privacy.s1Title` rendered as text in all 20 locales,
including English. The key is in `en.json` but `next-intl` returns
the key as a fallback instead of the value.

## Root cause
the platform's `en.json` has a **schema asymmetry**: some keys are
nested (object tree), some are flat-dotted (literal key with dots
in the name). For example:

```json
{
  "about": { "title": "About" },          // NESTED — t("about.title") works
  "home": { "eyebrow": "Welcome" },      // NESTED — t("home.eyebrow") works
  "privacy": {                            // MIXED:
    "title": "Privacy",                   //   NESTED — t("privacy.title") works
    "s1Title": "1. Information We Collect"  // FLAT-DOTTED — t("privacy.s1Title") is the literal lookup
  }
}
```

`next-intl` (and most i18n libs) treats `.` as a path separator by
default. So `t("privacy.s1Title")` walks:
- `messages["privacy"]` → exists (it's an object)
- `.s1Title` → undefined
- → returns the key as fallback

**Source:** next-intl docs on namespaces: https://next-intl-docs.vercel.app/docs/usage/messages

## Fix
Patch `getNested()` in `apps/web/src/i18n/loadMessages.ts` to first
check the literal flat-dotted key, then walk the dotted path:

```ts
function getNested(obj: Record<string, unknown>, dotted: string): unknown {
  // 1. Literal flat-dotted key at root (must not be an object)
  if (dotted in obj && typeof obj[dotted] !== 'object') {
    return obj[dotted];
  }
  // 2. Walk dotted path, but at each step try literal remainder
  const parts = dotted.split('.');
  let cur: unknown = obj;
  for (let i = 0; i < parts.length; i++) {
    if (cur === null || typeof cur !== 'object') return undefined;
    const curObj = cur as Record<string, unknown>;
    const remainder = parts.slice(i).join('.');
    // Literal flat-dotted at this level
    if (remainder in curObj && typeof curObj[remainder] !== 'object') {
      return curObj[remainder];
    }
    // Nested descent
    if (parts[i]! in curObj) {
      cur = curObj[parts[i]!];
    } else {
      return undefined;
    }
  }
  return cur;
}
```

The fix handles BOTH patterns transparently. The same logic is
in the Python merge script (`merge_locale.py:get_value`) — keep
them in sync.

## Verification
- **Test:** `test/i18n.test.ts > getNested handles flat-dotted and nested keys`
  — passes for all 2507 leaves × 20 locales
- **Live:** `https://87cff4b3.the platform-ca0.pages.dev` — `/privacy` and
  `/terms` render translated text instead of raw keys
- **Visual QA:** 180 screenshots in `/workspace/visual-qa/postfix_screenshots/`
  show 0 raw-key leaks across 20 locales × 9 pages

## Gotchas
- **`typeof undefined !== "object"` returns true.** Use
  `!== undefined` instead, or `obj !== null && typeof obj === 'object'`.
  The original naive check returned undefined too eagerly.
- **The merge script's get_value and the TS getNested MUST stay in sync.**
  If you fix one, fix the other. The two diverged once (2026-07-23)
  and the bug took a full Visual QA pass to catch.
- **Don't add a third pattern.** If you find a new key in en.json
  that doesn't fit nested OR flat-dotted, you've discovered a new
  schema smell. Either rename the key or fix en.json — don't extend
  the runtime helper.
- **Future refactor:** flatten en.json to all-nested OR all-flat.
  The dual-mode helper is a workaround for legacy data.

## Related
- the platform PR #i18n-getnested
- the platform PR #i18n-data-i18n (final i18n pass — uses the patched helper)
- a sibling repo has the same issue in `mc.json` (orchestrds.com's
  internal translation bundle) — tracked separately
- Python `get_value` reference: see `scripts/i18n/merge_locale.py`
