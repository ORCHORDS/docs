# Visual Regression Testing with Playwright + R2 Baseline Storage

Date: 2026-08-24
Author: example.com
Status: production

---

## Symptom / Use-case

A Cloudflare Worker serves an HTML dashboard (or API responses consumed by a frontend). After a CSS or template change, the layout shifts in unexpected ways that unit tests cannot catch. The team needs to compare screenshots of rendered pages before and after a change, but has no shared baseline storage that persists across CI runs. Git LFS is rejected due to cost, and the test runner's local disk is ephemeral.

---

## Context

Playwright captures full-page or element-level screenshots by driving a real Chromium, Firefox, or WebKit browser. R2 (Cloudflare's S3-compatible object storage) serves as a durable, globally-available baseline store. The workflow is:

1. CI takes a screenshot of the target Worker's rendered output.
2. CI downloads the baseline image from R2 (if it exists).
3. CI compares the two images with a pixel-diff library.
4. If the diff exceeds a threshold, CI fails and uploads the diff image to R2 for inspection.
5. When a visual change is intentional, the developer runs an update script that overwrites the R2 baseline.

Stack:
- `@playwright/test` ^1.46+
- `pixelmatch` ^5.x (pixel diff)
- `pngjs` ^7.x (PNG manipulation)
- `@aws-sdk/client-s3` ^3.x (R2 is S3-compatible)
- `wrangler` (for deploying and `wrangler dev`)
- TypeScript 5.x

---

## Solution

### 1. Install dependencies

```bash
npm install --save-dev \
  @playwright/test \
  pixelmatch \
  pngjs \
  @aws-sdk/client-s3

npx playwright install chromium
```

### 2. R2 client helper

```typescript
// tests/visual/r2-client.ts
import {
  S3Client,
  GetObjectCommand,
  PutObjectCommand,
  HeadObjectCommand,
} from '@aws-sdk/client-s3';
import type { Readable } from 'node:stream';

const R2_ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const R2_ACCESS_KEY  = process.env.R2_ACCESS_KEY_ID!;
const R2_SECRET_KEY  = process.env.R2_SECRET_ACCESS_KEY!;
const BUCKET         = process.env.R2_BUCKET ?? 'visual-baselines';

export const r2 = new S3Client({
  region: 'auto',
  endpoint: `https://${R2_ACCOUNT_ID}.r2.cloudflarestorage.com`,
  credentials: {
    accessKeyId:     R2_ACCESS_KEY,
    secretAccessKey: R2_SECRET_KEY,
  },
});

/** Download a baseline PNG from R2. Returns null if key does not exist. */
export async function downloadBaseline(key: string): Promise<Buffer | null> {
  try {
    await r2.send(new HeadObjectCommand({ Bucket: BUCKET, Key: key }));
  } catch {
    return null;
  }

  const res = await r2.send(new GetObjectCommand({ Bucket: BUCKET, Key: key }));
  const stream = res.Body as Readable;
  const chunks: Buffer[] = [];
  for await (const chunk of stream) chunks.push(Buffer.from(chunk));
  return Buffer.concat(chunks);
}

/** Upload a PNG buffer to R2 at the given key. */
export async function uploadToR2(
  key:         string,
  buffer:      Buffer,
  contentType: string = 'image/png',
): Promise<string> {
  await r2.send(
    new PutObjectCommand({
      Bucket:      BUCKET,
      Key:         key,
      Body:        buffer,
      ContentType: contentType,
    }),
  );
  return `https://${BUCKET}.${R2_ACCOUNT_ID}.r2.cloudflarestorage.com/${key}`;
}
```

### 3. Pixel-diff helper

```typescript
// tests/visual/diff.ts
import pixelmatch from 'pixelmatch';
import { PNG }    from 'pngjs';

export interface DiffResult {
  diffPixels:   number;
  totalPixels:  number;
  diffRatio:    number;
  diffBuffer:   Buffer;
}

/** Compare two PNG buffers and return a diff result. */
export function diffImages(baseline: Buffer, current: Buffer): DiffResult {
  const baseImg = PNG.sync.read(baseline);
  const currImg = PNG.sync.read(current);

  const width  = Math.max(baseImg.width,  currImg.width);
  const height = Math.max(baseImg.height, currImg.height);

  const expandedBase = new PNG({ width, height });
  const expandedCurr = new PNG({ width, height });
  PNG.bitblt(baseImg, expandedBase, 0, 0, baseImg.width, baseImg.height, 0, 0);
  PNG.bitblt(currImg, expandedCurr, 0, 0, currImg.width, currImg.height, 0, 0);

  const diffImg    = new PNG({ width, height });
  const diffPixels = pixelmatch(
    expandedBase.data,
    expandedCurr.data,
    diffImg.data,
    width,
    height,
    { threshold: 0.1, includeAA: false },
  );

  const totalPixels = width * height;
  return {
    diffPixels,
    totalPixels,
    diffRatio:  diffPixels / totalPixels,
    diffBuffer: PNG.sync.write(diffImg),
  };
}
```

### 4. Playwright visual regression fixture

```typescript
// tests/visual/fixtures.ts
import { test as base, expect } from '@playwright/test';
import { downloadBaseline, uploadToR2 } from './r2-client';
import { diffImages }                   from './diff';

const DIFF_THRESHOLD    = parseFloat(process.env.VISUAL_DIFF_THRESHOLD ?? '0.002');
const UPDATE_BASELINES  = process.env.UPDATE_BASELINES === 'true';

export const test = base.extend<{
  visualSnapshot: (name: string, options?: { clip?: { x: number; y: number; width: number; height: number } }) => Promise<void>;
}>({
  visualSnapshot: async ({ page }, use, testInfo) => {
    await use(async (name, options = {}) => {
      const screenshotBuffer = await page.screenshot({
        fullPage: true,
        ...options,
      });

      const key = `baselines/${testInfo.project.name}/${name}.png`;

      if (UPDATE_BASELINES) {
        const url = await uploadToR2(key, screenshotBuffer);
        console.log(`Baseline updated: ${url}`);
        return;
      }

      const baseline = await downloadBaseline(key);

      if (!baseline) {
        await uploadToR2(key, screenshotBuffer);
        console.log(`New baseline created for: ${name}`);
        return;
      }

      const { diffRatio, diffBuffer, diffPixels, totalPixels } = diffImages(baseline, screenshotBuffer);

      if (diffRatio > DIFF_THRESHOLD) {
        const diffKey    = `diffs/${testInfo.project.name}/${name}-diff-${Date.now()}.png`;
        const currentKey = `diffs/${testInfo.project.name}/${name}-current-${Date.now()}.png`;
        const diffUrl    = await uploadToR2(diffKey, diffBuffer);
        const currentUrl = await uploadToR2(currentKey, screenshotBuffer);

        await testInfo.attach('diff-image',         { body: diffBuffer,        contentType: 'image/png' });
        await testInfo.attach('current-screenshot', { body: screenshotBuffer,  contentType: 'image/png' });

        throw new Error(
          `Visual regression detected for "${name}": ${diffPixels}/${totalPixels} pixels differ ` +
          `(${(diffRatio * 100).toFixed(2)}% > ${(DIFF_THRESHOLD * 100).toFixed(2)}% threshold).\n` +
          `Diff: ${diffUrl}\nCurrent: ${currentUrl}\n` +
          `To update baseline: UPDATE_BASELINES=true npx playwright test`,
        );
      }
    });
  },
});

export { expect };
```

### 5. Visual regression tests against a deployed Worker

```typescript
// tests/visual/dashboard.spec.ts
import { test, expect } from './fixtures';

const WORKER_URL = process.env.WORKER_URL ?? 'http://localhost:8787';

test.describe('dashboard visual regression', () => {
  test.use({ viewport: { width: 1280, height: 720 } });

  test('home page matches baseline', async ({ page, visualSnapshot }) => {
    await page.goto(`${WORKER_URL}/`);
    await page.waitForLoadState('networkidle');
    await visualSnapshot('home-page');
  });

  test('order list matches baseline', async ({ page, visualSnapshot }) => {
    await page.goto(`${WORKER_URL}/orders`);
    await page.waitForSelector('[data-testid="order-list"]');
    await visualSnapshot('order-list', {
      clip: await page.locator('[data-testid="order-list"]').boundingBox() ?? undefined,
    });
  });

  test('mobile viewport matches baseline', async ({ page, visualSnapshot }) => {
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(`${WORKER_URL}/`);
    await page.waitForLoadState('networkidle');
    await visualSnapshot('home-page-mobile');
  });
});
```

### 6. `playwright.config.ts`

```typescript
// playwright.config.ts
import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: 'tests/visual',
  fullyParallel: false,
  retries: 0,
  reporter: [
    ['html', { open: 'never', outputFolder: 'reports/playwright' }],
    ['json', { outputFile: 'reports/playwright/results.json' }],
  ],
  use: {
    headless:   true,
    screenshot: 'only-on-failure',
    video:      'off',
  },
  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
  webServer: process.env.WORKER_URL ? undefined : {
    command:             'npx wrangler dev --local --port 8787',
    url:                 'http://localhost:8787',
    reuseExistingServer: !process.env.CI,
    timeout:             30_000,
  },
});
```

### 7. CI pipeline

```yaml
# .github/workflows/visual-regression.yml
name: Visual Regression

on:
  pull_request:

jobs:
  visual-regression:
    runs-on: ubuntu-latest
    env:
      CF_ACCOUNT_ID:         ${{ secrets.CF_ACCOUNT_ID }}
      R2_ACCESS_KEY_ID:      ${{ secrets.R2_ACCESS_KEY_ID }}
      R2_SECRET_ACCESS_KEY:  ${{ secrets.R2_SECRET_ACCESS_KEY }}
      R2_BUCKET:             visual-baselines
      WORKER_URL:            ${{ secrets.STAGING_WORKER_URL }}
      VISUAL_DIFF_THRESHOLD: '0.002'

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'npm'

      - run: npm ci
      - run: npx playwright install --with-deps chromium

      - name: Run visual regression tests
        run: npx playwright test

      - name: Upload Playwright report
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: playwright-report
          path: reports/playwright/
```

### 8. Baseline update workflow

```bash
# Update all baselines (intentional design change)
UPDATE_BASELINES=true WORKER_URL=https://staging.example.workers.dev npx playwright test

# Update a single baseline
UPDATE_BASELINES=true npx playwright test --grep 'home page matches baseline'
```

---

## Implementation Details

- R2 keys follow a `baselines/{project}/{test-name}.png` convention. Using Playwright's `testInfo.project.name` as a path segment allows storing baselines per browser/device project without key collisions.
- `pixelmatch` with `threshold: 0.1` tolerates per-pixel color differences up to 10% (on a 0-1 scale per channel). `includeAA: false` ignores anti-aliased edges, which vary between rendering environments.
- The `DIFF_THRESHOLD` of 0.2% (0.002) allows for minor sub-pixel rendering differences between CI environments without false positives. Tighten to 0.001 for pixel-perfect requirements.
- Diff images are uploaded to an R2 `diffs/` prefix with a timestamp in the key, so multiple PR runs do not overwrite each other's diffs.
- Playwright attaches images directly to the test report using `testInfo.attach()`, so failed tests show the diff inline in the HTML report without needing to visit R2.
- The `UPDATE_BASELINES` env variable gates baseline writes. Never set this to `true` in the main CI pipeline - only in deliberate update runs.

---

## Anti-patterns

- **Storing baselines in the git repository**: PNG files bloat the repository and diffs are unreadable. Use R2 (or another object store) as shown.
- **Using `page.waitForTimeout()` before screenshots**: Fixed timeouts are flaky. Always wait for a specific element or `networkidle` before capturing.
- **Running visual tests with `fullyParallel: true`**: Parallel test execution can cause resource contention on the Worker under test, producing rendering artifacts that trigger false diff failures.
- **Setting `DIFF_THRESHOLD` to 0**: Zero tolerance fails on any sub-pixel anti-aliasing difference and produces noise. Set a small but non-zero threshold.
- **Comparing API JSON responses as screenshots**: Render HTML/UI in a real browser. For JSON contract testing, use Pact (see `workers-contract-testing-pact.md`).
- **Updating baselines on every CI run**: Baselines must only be updated deliberately. Auto-updating them hides real regressions.

---

## Gotchas

- Chromium rendering on Linux CI differs subtly from macOS or Windows due to font rendering and GPU rasterization. Use a fixed Linux CI runner and pin the Playwright version to avoid baseline drift.
- R2 `GetObject` for large PNG files (> 5 MB) may hit Cloudflare's default response timeout in some regions. Compress screenshots with `page.screenshot({ type: 'jpeg', quality: 85 })` for smaller files at the cost of lossless color fidelity.
- The `HeadObjectCommand` used to check baseline existence will throw a `NoSuchKey` error with status 404. The try/catch in `downloadBaseline()` handles this. Do not use `GetObjectCommand` speculatively - it streams the full body before an error can be thrown.
- R2 is eventually consistent for overwrite operations. If a baseline is updated and a CI run starts within seconds, it may still receive the old baseline. Add a brief wait or use a versioned key scheme for high-frequency update workflows.
- `page.screenshot({ fullPage: true })` captures the entire scrollable page. For Workers that return very long HTML pages, the PNG can be several MB. Use `clip` to capture only the relevant component.
- Playwright's `webServer` option in `playwright.config.ts` starts `wrangler dev` automatically for local development but is skipped when `WORKER_URL` is set, ensuring CI tests run against the actual staging deployment.

---

## Verification

```bash
# First run - creates baselines in R2
WORKER_URL=https://staging.example.workers.dev npx playwright test

# Second run - compares against R2 baselines
WORKER_URL=https://staging.example.workers.dev npx playwright test

# View HTML report
npx playwright show-report reports/playwright

# Verify R2 baselines exist
npx wrangler r2 object list visual-baselines --prefix baselines/

# Update all baselines after an intentional redesign
UPDATE_BASELINES=true WORKER_URL=https://staging.example.workers.dev npx playwright test
```

---

## Related

- `documentation/categories/testing/workers-load-testing-k6-cloudflare.md`
- `documentation/categories/testing/workers-contract-testing-pact.md`
- `documentation/workers/r2-storage-patterns.md`
- `documentation/ci/github-actions-workers.md`

---

## Sources

- https://playwright.dev/docs/screenshots
- https://developers.cloudflare.com/r2/
- https://github.com/mapbox/pixelmatch
- https://developers.cloudflare.com/r2/api/s3/api/
- https://playwright.dev/docs/test-fixtures
