# continuous-localization-cicd

**Issue:** i18n continuous localization — CI/CD pipeline
**Date:** 2026-08-09
**Status:** documented

## Symptom
You ship a feature in English. Translators get the
file 2 weeks later. German ships 1 month after
English. You wish you had continuous localization.

## Root cause
**Manual translation is slow.** Automate.

**Source:** Lokalise + Crowdin 2026.

## The "continuous localization" concept

Continuous localization:
- **DevOps:** For translation
- **Trigger:** CI/CD events
- **Sync:** Bidirectional
- **Result:** All locales ship together

The l10n is continuous.

## The "7-step process" pattern

For setup:
1. **Extract:** Source files
2. **Context:** Screenshots + dev notes
3. **AI pipeline:** Translate
4. **Translation:** AI + human
5. **QA:** Validate
6. **Human:** For sensitive
7. **Release:** Auto PR

The 7 are the process.

## The "i18n library" pattern

For choice:
- **i18next:** Node.js, cross-framework
- **ICU MessageFormat:** Standard
- **FormatJS:** React
- **Vue I18n:** Vue
- **ARB:** Flutter

The lib is per stack.

## The "extract" pattern

For source:
```bash
# i18next
i18next 'src/**/*.{ts,tsx}' \
  -o locales/en/translation.json

# React Intl
formatjs extract 'src/**/*.{ts,tsx}' \
  --out-file locales/en.json
```

The extract is per commit.

## The "key naming" pattern

For keys:
- **Generic:** `btn_1` ❌
- **Hierarchical:** `settings.privacy.toggle_label` ✅
- **Format:** `namespace.component.action`
- **Context:** Path-based for AI

The name is semantic.

## The "pseudolocalization" pattern

For QA:
- **Test:** Accented + doubled
- **Example:** `Edit` → `[!!! Ééððíítt !!!]`
- **Detect:** UI overflow, missing glyphs
- **Use:** Dev, not prod

The pseudo is per dev.

## The "ICU MessageFormat" pattern

For plurals:
```
❌ "You have " + count + " items"
✅ "{count, plural, one {# item} other {# items}}"
```

The ICU is per language.

## The "translation platform" pattern

For choice:
- **Lokalise:** GitHub Action, CLI
- **Crowdin:** GitHub Action, CLI
- **Phrase:** GitHub Action
- **Transifex:** CLI
- **DIY:** JSON files + PR

The platform is per need.

## The "Lokalise workflow" pattern

For Lokalise:
```yaml
# .github/workflows/lokalise.yml
name: Sync with Lokalise
on:
  push:
    branches: [main]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Push source
        run: |
          lokalise branch push \
            --project-id ${{ secrets.LOKALISE_ID }} \
            --branch main
      - name: Pull translations
        run: |
          lokalise branch pull \
            --project-id ${{ secrets.LOKALISE_ID }} \
            --branch main
```

The Lokalise is CLI.

## The "Crowdin workflow" pattern

For Crowdin:
```yaml
# .github/workflows/crowdin.yml
on:
  push:
    branches: [main]
jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Crowdin Sync
        uses: crowdin/github-action@v1
        with:
          upload_sources: true
          upload_translations: false
          download_translations: true
          create_pull_request: true
```

The Crowdin is Action.

## The "key naming convention" pattern

For keys:
- **Namespaced:** `auth.login.title`
- **Hierarchical:** `dashboard.widget.greeting`
- **Action:** `auth.login.button.submit`
- **Stable:** Never change

The name is stable.

## The "context for AI" pattern

For context:
- **Screenshots:** Auto from CI
- **Dev notes:** PR description
- **Visual:** Figma integration
- **Tech:** ICU syntax

The context is rich.

## The "AI translation" pattern

For AI:
- **Creative:** Claude 4, Gemini 3 (marketing)
- **Technical:** High-reasoning (logic, ICU)
- **Pipeline:** Multi-step (not one prompt)
- **QA:** Pseudoloc + placeholder check

The AI is per content.

## The "AI pipeline" pattern

For pipeline:
1. **Context gather:** Screenshots, notes
2. **Translate:** Specialized model
3. **Validate:** Placeholders, tags
4. **Pseudoloc test:** UI breaks?
5. **Store:** TMS

The pipeline is structured.

## The "automated QA" pattern

For QA:
- **Placeholder:** `{count}` preserved
- **Tag:** `<link>` not corrupted
- **Pseudoloc:** UI overflow check
- **Length:** Per locale budget

The QA is automated.

## The "human review" pattern

For human:
- **Sensitive:** Legal, privacy, billing
- **Brand:** Marketing copy
- **Complex:** Logic-in-text flagged
- **Not for:** "OK" buttons

The human is for stakes.

## The "automated PR" pattern

For PR:
- **Auto:** Platform opens
- **Includes:** All locales (20+)
- **Single merge:** One click
- **Pre-merged:** Translation complete

The PR is auto.

## The "OTA for mobile" pattern

For mobile:
- **CDN:** Served at runtime
- **No app review:** iOS / Android skip
- **Fast:** Text fixes in hours
- **Use:** Small text + new languages

The OTA is for mobile.

## The "branch strategy" pattern

For branches:
- **Source:** `main` (en.json)
- **Translation:** `l10n/main`
- **PR:** From l10n → main
- **Conflict:** Resolve in l10n

The branch is dedicated.

## The "pseudoloc" pattern

For dev:
```typescript
// en.json (dev)
{
  "greeting": "Hello"
}
// en-pseudo.json
{
  "greeting": "[!!! Hééllóó !!!]"
}
```

The pseudo is in dev.

## The "no hardcoded strings" anti-pattern

For hardcoded:
- **Issue:** "Cancel" buried in JSX
- **Fix:** Externalize to JSON

The string is in JSON.

## The "concatenation" anti-pattern

For concat:
- **Issue:** "You have " + n + " items" breaks in DE
- **Fix:** ICU MessageFormat

The format is ICU.

## The "no context" anti-pattern

For no context:
- **Issue:** Translator guesses
- **Fix:** Screenshot + notes

The context is required.

## The "no pseudoloc" anti-pattern

For no pseudo:
- **Issue:** UI breaks in DE
- **Fix:** Pseudoloc in dev

The pseudo is required.

## The "no automated PR" anti-pattern

For no PR:
- **Issue:** Manual merge
- **Fix:** Auto PR from platform

The PR is automated.

## The "no CI integration" anti-pattern

For no CI:
- **Issue:** Strings drift
- **Fix:** CI syncs on push

The CI is integrated.

## The "extracted but not translated" anti-pattern

For extracted:
- **Issue:** Strings pending
- **Fix:** Track + alert

The flow is tracked.

## The "inconsistent keys" anti-pattern

For random:
- **Issue:** "btn_1" not findable
- **Fix:** Convention enforced

The key is convention.

## The "l10n checklist" pattern

For checklist:
- [ ] i18n lib chosen
- [ ] Keys externalized
- [ ] Naming convention
- [ ] Pseudoloc in dev
- [ ] ICU MessageFormat
- [ ] Platform connected
- [ ] CI sync on push
- [ ] Auto PR
- [ ] QA automated
- [ ] Human for sensitive
- [ ] OTA for mobile

The checklist is 11.

## Verification
- **Test:** Extract on commit
- **Test:** Sync to platform
- **Test:** Translation back
- **Test:** Pseudoloc passes
- **Test:** Auto PR works
- **Audit:** Quarterly

## Gotchas
- **The "hardcoded strings" anti-pattern.** JSON.
- **The "concatenation" anti-pattern.** ICU.
- **The "no context" anti-pattern.** Screenshot.

## Related
- `i18n/locale-data-and-cldr.md`
- `i18n/translation-pipeline.md`
- `i18n/icu-plural-rules-20-locales.md`
- `i18n/icu-messageformat-advanced.md`
- `i18n/data-i18n-marker-pattern.md`
- `patterns/feature-flags-best-practices.md`
- Lokalise: https://lokalise.com/blog/continuous-localization-101/
- Crowdin: https://crowdin.com/blog/software-localization
- TranslateLinker: https://www.translatelinker.com/blog/translation-cicd-workflow
