# Email Template Versioning and A/B Testing with R2 Storage

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: active

## Symptom / Use-case

Marketing teams iterate on email templates frequently but deployments couple template changes to code releases, making rollback difficult and A/B test result attribution unreliable. When a poorly-performing template variant ships to the full list before significance is reached, reverting requires a new deployment cycle rather than a configuration change. Storing versioned template artefacts in Cloudflare R2 and resolving the active variant at send time from a Worker decouples template lifecycle from application deployments and enables statistically rigorous split testing with mid-flight rollback.

## Context

Cloudflare R2 is an S3-compatible object storage service accessible from Workers via the `env.BUCKET` binding without egress fees. Template artefacts (HTML, MJML source, plain-text fallback, and metadata JSON) are stored as immutable versioned objects under a structured key prefix. A D1 database tracks experiment metadata — which template IDs are active for which experiment, their traffic weights, and current send/click/open counts. A Worker resolves the correct variant for each recipient at send time, stamps the chosen variant into the message for attribution, and later ingests webhook events (opens, clicks, unsubscribes) to update experiment metrics. Unlike feature flags in KV, R2 stores the full template body (which can exceed KV's 25 MB value limit for complex MJML-compiled templates).

## R2 Object Key Structure

```
templates/
  {template-slug}/
    versions/
      {version-id}.json          <- metadata
      {version-id}.html          <- compiled HTML (from MJML or Handlebars)
      {version-id}.txt           <- plain-text fallback
      {version-id}.mjml          <- MJML source (optional, for re-compilation)
    active                       <- points to latest production version ID (text file)
experiments/
  {experiment-id}.json           <- experiment config
```

### Version Metadata Schema

```json
{
  "version_id":   "20260822-143501-a3f9c",
  "template_slug": "welcome-email",
  "created_at":   1753192501,
  "created_by":   "ci@example.com",
  "git_sha":      "3e5a9f2",
  "description":  "Subject line test: question vs statement",
  "subject":      "Your account is ready — here's how to start",
  "preview_text": "Set up takes 2 minutes",
  "variables":    ["firstName", "activationUrl", "companyName"],
  "tags":         ["onboarding", "v3-redesign"]
}
```

## Worker — Template Upload CLI (Wrangler Script)

```typescript
// scripts/upload-template.ts  (Node.js, runs locally / in CI)
import { S3Client, PutObjectCommand } from '@aws-sdk/client-s3';
import { readFileSync } from 'node:fs';
import { createHash } from 'node:crypto';

const VERSION_ID = `${new Date().toISOString().replace(/[:.]/g, '').slice(0, 15)}-${
  createHash('sha256').update(Math.random().toString()).digest('hex').slice(0, 5)
}`;

async function uploadTemplateVersion(
  slug: string,
  htmlPath: string,
  txtPath: string,
  meta: object,
  r2Config: { accountId: string; accessKeyId: string; secretAccessKey: string; bucket: string }
): Promise<string> {
  const client = new S3Client({
    region: 'auto',
    endpoint: `https://${r2Config.accountId}.r2.cloudflarestorage.com`,
    credentials: {
      accessKeyId:     r2Config.accessKeyId,
      secretAccessKey: r2Config.secretAccessKey,
    },
  });

  const prefix = `templates/${slug}/versions/${VERSION_ID}`;
  const html   = readFileSync(htmlPath);
  const txt    = readFileSync(txtPath);

  await Promise.all([
    client.send(new PutObjectCommand({
      Bucket: r2Config.bucket, Key: `${prefix}.json`,
      Body: JSON.stringify({ version_id: VERSION_ID, ...meta }),
      ContentType: 'application/json',
    })),
    client.send(new PutObjectCommand({
      Bucket: r2Config.bucket, Key: `${prefix}.html`,
      Body: html, ContentType: 'text/html',
    })),
    client.send(new PutObjectCommand({
      Bucket: r2Config.bucket, Key: `${prefix}.txt`,
      Body: txt, ContentType: 'text/plain',
    })),
    client.send(new PutObjectCommand({
      Bucket: r2Config.bucket, Key: `templates/${slug}/active`,
      Body: VERSION_ID, ContentType: 'text/plain',
    })),
  ]);

  console.log(`Uploaded ${slug}@${VERSION_ID}`);
  return VERSION_ID;
}
```

## D1 Schema — Experiment Tracking

```sql
-- migrations/0001_ab_experiments.sql

CREATE TABLE IF NOT EXISTS template_experiments (
  id            TEXT PRIMARY KEY,       -- e.g. 'welcome-subj-aug26'
  template_slug TEXT NOT NULL,
  status        TEXT NOT NULL DEFAULT 'running',  -- 'running' | 'concluded' | 'paused'
  winner_variant TEXT,                  -- set when concluded
  traffic_pct   INTEGER NOT NULL DEFAULT 100,  -- % of recipients in experiment
  created_at    INTEGER NOT NULL DEFAULT (unixepoch()),
  concluded_at  INTEGER
);

CREATE TABLE IF NOT EXISTS experiment_variants (
  experiment_id TEXT NOT NULL REFERENCES template_experiments(id) ON DELETE CASCADE,
  variant_id    TEXT NOT NULL,          -- e.g. 'control' | 'treatment_a'
  version_id    TEXT NOT NULL,          -- R2 version ID
  weight        INTEGER NOT NULL,       -- integer weight (e.g. 50/50 or 70/30)
  sends         INTEGER NOT NULL DEFAULT 0,
  opens         INTEGER NOT NULL DEFAULT 0,
  clicks        INTEGER NOT NULL DEFAULT 0,
  unsubscribes  INTEGER NOT NULL DEFAULT 0,
  PRIMARY KEY (experiment_id, variant_id)
);

CREATE INDEX idx_exp_slug ON template_experiments (template_slug, status);
```

## Worker — Variant Assignment at Send Time

```typescript
// src/template-resolver.ts
export interface Env {
  BUCKET: R2Bucket;
  DB:     D1Database;
  KV:     KVNamespace;   // cache layer for template HTML
}

export interface ResolvedTemplate {
  versionId:   string;
  variantId:   string;
  experimentId: string | null;
  subject:     string;
  html:        string;
  text:        string;
}

/**
 * Assign a variant deterministically by hashing userId + experimentId,
 * so the same user always gets the same variant within an experiment.
 */
async function assignVariant(
  experimentId: string,
  userId: string,
  variants: Array<{ variant_id: string; weight: number }>
): Promise<string> {
  const hash = await crypto.subtle.digest(
    'SHA-256',
    new TextEncoder().encode(`${experimentId}:${userId}`)
  );
  const num  = new DataView(hash).getUint32(0) >>> 0;   // [0, 2^32)
  const total = variants.reduce((s, v) => s + v.weight, 0);
  const slot  = num % total;
  let acc = 0;
  for (const v of variants) {
    acc += v.weight;
    if (slot < acc) return v.variant_id;
  }
  return variants[0].variant_id;
}

export async function resolveTemplate(
  env: Env,
  templateSlug: string,
  userId: string,
  vars: Record<string, string>
): Promise<ResolvedTemplate> {
  // Check for a running experiment on this template
  const experiment = await env.DB
    .prepare(`SELECT * FROM template_experiments WHERE template_slug = ? AND status = 'running' LIMIT 1`)
    .bind(templateSlug)
    .first<{ id: string; traffic_pct: number }>();

  let versionId: string;
  let variantId = 'default';
  let experimentId: string | null = null;

  if (experiment && shouldEnroll(userId, experiment.traffic_pct)) {
    const variants = await env.DB
      .prepare(`SELECT variant_id, weight, version_id FROM experiment_variants WHERE experiment_id = ?`)
      .bind(experiment.id)
      .all<{ variant_id: string; weight: number; version_id: string }>();

    variantId    = await assignVariant(experiment.id, userId, variants.results);
    experimentId = experiment.id;
    const chosen = variants.results.find(v => v.variant_id === variantId)!;
    versionId    = chosen.version_id;

    // Record send
    await env.DB
      .prepare(`UPDATE experiment_variants SET sends = sends + 1
                WHERE experiment_id = ? AND variant_id = ?`)
      .bind(experiment.id, variantId).run();
  } else {
    // No experiment — read active version pointer from R2
    const activeObj = await env.BUCKET.get(`templates/${templateSlug}/active`);
    if (!activeObj) throw new Error(`No active version for template ${templateSlug}`);
    versionId = (await activeObj.text()).trim();
  }

  const [htmlObj, txtObj, metaObj] = await Promise.all([
    fetchCached(env, `templates/${templateSlug}/versions/${versionId}.html`),
    fetchCached(env, `templates/${templateSlug}/versions/${versionId}.txt`),
    fetchCached(env, `templates/${templateSlug}/versions/${versionId}.json`),
  ]);

  const meta    = JSON.parse(metaObj);
  const html    = renderTemplate(htmlObj, vars);
  const text    = renderTemplate(txtObj, vars);
  const subject = renderTemplate(meta.subject as string, vars);

  return { versionId, variantId, experimentId, subject, html, text };
}

async function fetchCached(env: Env, key: string): Promise<string> {
  const cached = await env.KV.get(key);
  if (cached) return cached;
  const obj = await env.BUCKET.get(key);
  if (!obj) throw new Error(`R2 object not found: ${key}`);
  const text = await obj.text();
  // Cache for 5 minutes — short enough to pick up rollbacks
  await env.KV.put(key, text, { expirationTtl: 300 });
  return text;
}

function shouldEnroll(userId: string, trafficPct: number): boolean {
  // Deterministic bucketing: same user always in or out
  const n = parseInt(userId.replace(/\D/g, '').slice(-4) || '0', 10);
  return (n % 100) < trafficPct;
}

function renderTemplate(template: string, vars: Record<string, string>): string {
  // Simple {{variable}} substitution — replace with Handlebars in production
  return template.replace(/\{\{(\w+)\}\}/g, (_, k) => vars[k] ?? '');
}
```

## Rollback — Pinning a Previous Version

```typescript
// src/rollback.ts
export async function rollbackTemplate(
  bucket: R2Bucket,
  kv: KVNamespace,
  templateSlug: string,
  targetVersionId: string
): Promise<void> {
  // Verify target version exists
  const check = await bucket.head(`templates/${templateSlug}/versions/${targetVersionId}.html`);
  if (!check) throw new Error(`Version ${targetVersionId} not found in R2`);

  // Update active pointer
  await bucket.put(`templates/${templateSlug}/active`, targetVersionId, {
    customMetadata: { rolledBackAt: new Date().toISOString() },
  });

  // Bust KV cache for this template's active pointer and HTML
  await Promise.all([
    kv.delete(`templates/${templateSlug}/active`),
    kv.delete(`templates/${templateSlug}/versions/${targetVersionId}.html`),
    kv.delete(`templates/${templateSlug}/versions/${targetVersionId}.txt`),
  ]);
}
```

## Mobile vs Desktop Email Rendering Considerations

- **Template preview at upload**: run a headless Chromium screenshot (via Puppeteer in a Node CI step) at 375 px (mobile) and 1280 px (desktop) widths before committing a new version. Store screenshots as `versions/{version-id}-mobile.png` and `versions/{version-id}-desktop.png` in R2 for the design review workflow.
- **Plain-text fallback**: every versioned template must include a `.txt` artefact. Plain-text renders in some corporate email gateways that strip HTML; it is also the fallback used by screen readers and some SMS forwarding gateways.
- **MJML compilation in CI**: compile MJML → HTML in the CI pipeline (not in the Worker) and store the compiled HTML in R2. Worker-side MJML compilation adds ~150 ms cold-start latency and exceeds the 1 MB script size limit if bundled.
- **Outlook conditional comments**: compiled MJML includes `<!--[if mso]>` Outlook VML conditionals. Preserve them verbatim during template storage; never run the stored HTML through an HTML minifier that strips comments.
- **Font stack fallback**: mobile email clients (Gmail iOS, Outlook Android) download Google Fonts sporadically. Always specify `font-family: 'Inter', -apple-system, Arial, sans-serif` — the system-font fallback renders correctly even when the web font is blocked.

## Anti-patterns

- **Storing compiled HTML in D1 TEXT columns**: D1 SQLite stores TEXT as UTF-8 with a 1 GB per-database limit but 16 MB per-row limit. A complex MJML-compiled template with inlined images can exceed 1 MB; R2 has no per-object size limit and is cheaper per GB.
- **Using wall-clock random assignment** for A/B variants: the same user receives different variants across sessions. Always use a deterministic hash of userId + experimentId.
- **Caching templates in KV indefinitely**: if a rollback is issued, stale cached HTML continues to be served until TTL expiry. Use a short TTL (5–10 minutes) and bust the cache key explicitly on rollback.
- **Concluding an experiment based on total sends, not statistical significance**: use a two-proportion z-test or a Bayesian beta-binomial model; declare a winner only when p < 0.05 (frequentist) or posterior probability of being best > 0.95 (Bayesian).
- **A/B testing subject lines and body copy simultaneously**: changes are not isolatable. Test one variable per experiment.

## Gotchas

- R2 `list()` operations do not guarantee ordering by created time; rely on version IDs that embed a sortable timestamp prefix rather than listing to find the latest version.
- KV `put` with `expirationTtl` has a minimum of 60 seconds; using 0 or a negative value throws. Template cache TTL must be at least 60 s.
- When running multiple concurrent experiments on the same template (e.g. subject line experiment overlapping a body experiment), ensure variant assignment functions are independent — different `experimentId` seeds produce non-correlated assignments.
- R2 presigned URLs are not natively supported via the Worker binding (only via the S3-compatible API); for internal CI preview pages, generate short-lived signed tokens rather than making the R2 bucket public.

## Verification

```bash
# List available versions for a template
npx wrangler r2 object get templates/welcome-email/active --pipe

# Check active experiment metrics
npx wrangler d1 execute DB --command \
  "SELECT ev.variant_id, ev.sends, ev.opens,
          ROUND(100.0*ev.opens/NULLIF(ev.sends,0),2) AS open_rate_pct
   FROM experiment_variants ev
   JOIN template_experiments te ON te.id = ev.experiment_id
   WHERE te.template_slug = 'welcome-email' AND te.status = 'running';"

# Trigger rollback via Worker API
curl -X POST https://your-worker.workers.dev/admin/templates/welcome-email/rollback \
  -H 'Authorization: Bearer $ADMIN_TOKEN' \
  -H 'Content-Type: application/json' \
  -d '{"targetVersionId":"20260801-120000-b1a2c"}'
```

## Related

- `email-a-b-testing.md`
- `email-template-versioning.md`
- `email-template-mjml-cloudflare-pages.md`
- `handlebars-email-templates.md`
- `react-email-template-system.md`
- `email-dynamic-content.md`

## Sources

- Cloudflare R2 Workers binding — https://developers.cloudflare.com/r2/api/workers/workers-api-reference/
- Cloudflare KV — https://developers.cloudflare.com/kv/
- MJML framework — https://mjml.io/
- Two-proportion z-test for A/B email experiments — https://www.evanmiller.org/ab-testing/sample-size.html
- RFC 2822 — Internet Message Format (plain-text fallback requirements)
