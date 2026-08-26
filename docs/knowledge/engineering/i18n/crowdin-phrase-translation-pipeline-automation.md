# Crowdin and Phrase: Translation Pipeline Automation in CI/CD

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

Localization files drift out of sync with source code: developers merge new feature strings
but translators only learn about them days later via a Slack message. Review cycles happen
in Google Docs, TM leverage is never applied, and every release ships with untranslated
fallback strings in production.

You need an automated pipeline where source-string changes in version control trigger
translator tasks, completed translations get committed back automatically, and the build
fails loudly when coverage drops below a configured threshold.

## Context

**Crowdin** (crowdin.com) and **Phrase** (formerly Memsource, phrase.com) are the two
dominant cloud TMS platforms for developer-led localization. Both offer:

- REST APIs and CLI tools for pushing/pulling files
- GitHub/GitLab/Bitbucket native integrations via OAuth app or webhook
- Translation memory (TM) and machine-translation (MT) engines
- In-context editing and screenshot upload
- Webhooks for build-status callbacks

They differ in positioning: Crowdin targets developer-centric open-source and SaaS
products; Phrase (the full Phrase Strings + Phrase TMS suite) targets enterprise accounts
with complex workflows and strict reviewer hierarchies.

Both are compatible with the same file formats: JSON, XLIFF 1.2/2.0, PO/POT, ARB,
Android strings.xml, iOS .strings/.stringsdict, and YAML.

## Crowdin CLI + GitHub Actions

### Installation

```yaml
# .github/workflows/crowdin-sync.yml
name: Crowdin Sync

on:
  push:
    branches: [main]
    paths:
      - 'src/locales/en/**'
  schedule:
    - cron: '0 6 * * 1'   # pull translations every Monday 06:00 UTC

jobs:
  crowdin:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Upload sources and download translations
        uses: crowdin/github-action@v2
        with:
          upload_sources: true
          download_translations: true
          create_pull_request: true
          localization_branch_name: l10n/crowdin-updates
          commit_message: 'chore(i18n): sync translations from Crowdin'
          pull_request_title: '[i18n] Crowdin translation updates'
          pull_request_labels: 'i18n, automated'
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          CROWDIN_PROJECT_ID: ${{ secrets.CROWDIN_PROJECT_ID }}
          CROWDIN_PERSONAL_TOKEN: ${{ secrets.CROWDIN_PERSONAL_TOKEN }}
```

### crowdin.yml project config

```yaml
# crowdin.yml (repo root)
project_id_env: CROWDIN_PROJECT_ID
api_token_env: CROWDIN_PERSONAL_TOKEN

preserve_hierarchy: true

files:
  - source: /src/locales/en/*.json
    translation: /src/locales/%two_letters_code%/%original_file_name%
    update_option: update_as_unapproved
    escape_quotes: 0
```

`update_as_unapproved` ensures that when a source string changes the existing translation
is preserved in TM but marked for review — translators are notified without losing prior
work.

## Phrase CLI + GitHub Actions

### Installation and auth

```bash
npm install --save-dev @phrase/cli   # or brew install phrase/tap/phrase
```

```yaml
# .github/workflows/phrase-sync.yml
name: Phrase Sync

on:
  push:
    branches: [main]
    paths: ['src/locales/en.json']

jobs:
  push-sources:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Push source strings to Phrase
        run: |
          npx phrase push \
            --project-id "$PHRASE_PROJECT_ID" \
            --file-format json \
            --source src/locales/en.json \
            --locale-id en
        env:
          PHRASE_ACCESS_TOKEN: ${{ secrets.PHRASE_ACCESS_TOKEN }}
          PHRASE_PROJECT_ID: ${{ secrets.PHRASE_PROJECT_ID }}

  pull-translations:
    runs-on: ubuntu-latest
    needs: []   # run independently on schedule
    if: github.event_name == 'schedule'
    steps:
      - uses: actions/checkout@v4
        with:
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Pull translations
        run: |
          npx phrase pull \
            --project-id "$PHRASE_PROJECT_ID" \
            --file-format json \
            --target 'src/locales/<locale_code>.json'
        env:
          PHRASE_ACCESS_TOKEN: ${{ secrets.PHRASE_ACCESS_TOKEN }}
          PHRASE_PROJECT_ID: ${{ secrets.PHRASE_PROJECT_ID }}

      - name: Commit and push
        uses: stefanzweifel/git-auto-commit-action@v5
        with:
          commit_message: 'chore(i18n): pull translations from Phrase'
          branch: l10n/phrase-updates
          create_branch: true
```

### .phrase.yml

```yaml
phrase:
  access_token: <%= ENV['PHRASE_ACCESS_TOKEN'] %>
  project_id: <%= ENV['PHRASE_PROJECT_ID'] %>
  file_format: json

push:
  sources:
    - file: ./src/locales/en.json
      params:
        locale_id: en
        update_translations: false   # never overwrite approved translations with source values

pull:
  targets:
    - file: ./src/locales/<locale_code>.json
      params:
        include_unverified_translations: false  # only pull approved strings
        fallback_locale_id: en
```

## Translation Coverage Gate

Add a coverage check before the build proceeds to production:

```javascript
// scripts/check-i18n-coverage.mjs
import { readdirSync, readFileSync } from 'fs';
import { join } from 'path';

const THRESHOLD = 0.95;   // 95 % minimum
const SOURCE_LOCALE = 'en';
const LOCALES_DIR = './src/locales';

const source = JSON.parse(
  readFileSync(join(LOCALES_DIR, `${SOURCE_LOCALE}.json`), 'utf8')
);
const sourceKeys = new Set(Object.keys(source));

let failed = false;
for (const file of readdirSync(LOCALES_DIR)) {
  const locale = file.replace('.json', '');
  if (locale === SOURCE_LOCALE) continue;

  const target = JSON.parse(readFileSync(join(LOCALES_DIR, file), 'utf8'));
  const coverage = Object.keys(target).filter(k => sourceKeys.has(k)).length / sourceKeys.size;

  console.log(`${locale}: ${(coverage * 100).toFixed(1)}%`);
  if (coverage < THRESHOLD) {
    console.error(`  FAIL — below ${(THRESHOLD * 100)}% threshold`);
    failed = true;
  }
}
process.exit(failed ? 1 : 0);
```

Wire it into CI before the build step:

```yaml
- name: Check translation coverage
  run: node scripts/check-i18n-coverage.mjs
```

## Webhook-Driven Build Triggers

Both platforms can POST a webhook when all strings for a locale are translated and
approved, enabling you to trigger a production deployment automatically:

### Crowdin webhook (project settings → Integrations → Webhooks)

```
Event: "All strings translated" or "All strings approved"
URL:   https://api.github.com/repos/ORG/REPO/dispatches
Headers: Authorization: token <PAT>
Body:   { "event_type": "crowdin-approved", "client_payload": { "locale": "de" } }
```

Listen in CI:

```yaml
on:
  repository_dispatch:
    types: [crowdin-approved]
```

## Screenshot-Based In-Context Review

Both platforms accept screenshot uploads linked to string keys so translators see visual
context. Automate with Playwright:

```typescript
// scripts/upload-screenshots.ts
import { chromium } from 'playwright';
import { uploadScreenshot } from './crowdin-api'; // thin wrapper around REST API

const LOCALES = ['en'];
const ROUTES = ['/dashboard', '/settings/profile'];

const browser = await chromium.launch();
for (const route of ROUTES) {
  const page = await browser.newPage();
  await page.goto(`http://localhost:3000${route}`);
  const buf = await page.screenshot({ fullPage: true });
  await uploadScreenshot(buf, route);   // tags screenshot to string keys via data-i18n attrs
  await page.close();
}
await browser.close();
```

## Anti-patterns

- **Committing directly to main from the pipeline** — always open a PR so translators'
  changes are reviewed. Automated commits to main bypass branch protection rules and can
  conflict with in-flight feature branches.
- **Pushing all locales at once without TM pre-translation** — run MT + TM leverage
  before pushing to translators; batch-pushing raw strings inflates billable word counts.
- **Skipping `update_as_unapproved`** — if source strings silently overwrite approved
  translations, linguists never know a string changed.
- **Hardcoding project IDs in YAML** — always use secrets; Crowdin project IDs are not
  sensitive, but API tokens absolutely are.
- **Pulling unverified translations to production** — always set `include_unverified:
  false` when pulling to a release branch.

## Gotchas

- Crowdin's GitHub action creates PRs from a machine account; configure branch protection
  to allow the Crowdin bot to bypass required reviews, or use an app token with bypass
  permission.
- Phrase's `<locale_code>` placeholder uses IETF BCP 47 tags (`pt-BR`), not two-letter
  codes; verify your directory structure matches before the first sync.
- Both CLIs cache auth tokens locally; on ephemeral CI runners, always pass credentials
  via env vars, not config files.
- String deletions in Crowdin are soft-deletes by default — removed source strings remain
  in TM and do not delete translated strings unless you explicitly archive them via the
  API.
- Phrase's pull command will silently skip a locale if no translation exists yet. Add an
  explicit check for missing locale files after pull.

## Verification

```bash
# Crowdin: check project status via API
curl -H "Authorization: Bearer $CROWDIN_PERSONAL_TOKEN" \
  "https://api.crowdin.com/api/v2/projects/$CROWDIN_PROJECT_ID/languages/progress"

# Phrase: check locale completion
curl -H "Authorization: token $PHRASE_ACCESS_TOKEN" \
  "https://api.phrase.com/v2/projects/$PHRASE_PROJECT_ID/locales" | \
  jq '[.[] | {locale: .name, translated: .statistics.translations_completed_percent}]'
```

Run the coverage script locally before raising a release PR:

```bash
node scripts/check-i18n-coverage.mjs && echo "Coverage OK"
```

## Related

- `tolgee-weblate-transifex-comparison-2026.md`
- `continuous-localization-cicd.md`
- `translation-memory-2026.md`
- `xliff-format-handling.md`
- `mt-quality-evaluation-2026.md`

## Sources

- Crowdin GitHub Action documentation: https://github.com/crowdin/github-action
- Phrase CLI reference: https://phrase.com/cli/
- Crowdin REST API v2: https://developer.crowdin.com/api/v2/
- Phrase API v2: https://developers.phrase.com/api/
- OASIS XLIFF 2.0 spec for file format interop
