# screenshot-based-translation

**Issue:** Providing visual context to translators via screenshots linked to translation keys
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Translators working with only key-value pairs mistranslate UI strings without visual context. Screenshots reduce revision rounds by 30-50%.

## Pattern / Solution
Instrument components:
```tsx
<h1 data-i18n="hero.title">{t('hero.title')}</h1>
```
Automated capture with Playwright:
```ts
import { chromium } from 'playwright';
const browser = await chromium.launch();
const page = await browser.newPage();
const keys = ['nav.home', 'hero.title'];
for (const key of keys) {
  await page.goto(`http://localhost:3000?highlight=${key}`);
  await page.locator(`[data-i18n="${key}"]`).screenshot({
    path: `screenshots/${key.replace(/\./g, '_')}.png`
  });
}
```
Upload to TMS:
```bash
phrase screenshots upload \
  --project-id $PROJECT \
  --screenshot screenshots/*.png \
  --auto-tag-keys
```

## Gotchas
- Screenshots must be regenerated after UI layout changes; stale screenshots mislead translators
- Auto-tagging by position is imprecise; manual key mapping is more reliable
- Modals/tooltips require triggering the interaction state before capture

## Related
- `translation-context-notes.md`
- `translation-quality-metrics.md`
