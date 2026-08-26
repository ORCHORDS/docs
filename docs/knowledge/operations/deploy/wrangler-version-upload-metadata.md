# Wrangler Version Upload with Metadata

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

You need to annotate each uploaded Worker version with build provenance — git SHA, CI run ID, deployer identity, or semantic version — so that rollback, audit, and traffic-split operations reference human-readable version labels rather than opaque UUIDs. Without metadata, `wrangler versions list` shows version IDs only, making it impossible to correlate a live version to its originating commit or pipeline run.

## Context

`wrangler versions upload` (Workers Deployments API) separates the **upload** step (creating a version artifact) from the **deploy** step (routing traffic to it). Versions accept a `--tag` and `--message` flag that persist as immutable metadata on the version record. This enables labelled canary splits, traceable rollbacks, and audit trails without a separate version-tracking service. The pattern requires `workers_dev = false` and explicit deployment configuration in `wrangler.toml`.

---

## 1. Basic Version Upload with Tag and Message

Upload a version with build metadata before deploying. The version stays dormant (receives 0% traffic) until explicitly promoted.

```bash
# In CI — capture metadata from environment
wrangler versions upload \
  --tag "v$(node -p "require('./package.json').version")-${GITHUB_SHA:0:8}" \
  --message "build: #${GITHUB_RUN_NUMBER} by ${GITHUB_ACTOR} on ${GITHUB_REF_NAME}"
```

```typescript
// scripts/upload-version.ts
import { execSync } from 'child_process';

const pkg    = require('../package.json');
const sha    = (process.env.GITHUB_SHA ?? 'local').slice(0, 8);
const runId  = process.env.GITHUB_RUN_NUMBER ?? '0';
const actor  = process.env.GITHUB_ACTOR ?? 'local';
const branch = process.env.GITHUB_REF_NAME ?? 'dev';

const tag     = `v${pkg.version}-${sha}`;
const message = `build #${runId} | branch: ${branch} | by: ${actor}`;

execSync(
  `npx wrangler versions upload --tag "${tag}" --message "${message}"`,
  { stdio: 'inherit' }
);

console.log(`Uploaded version tag: ${tag}`);
```

---

## 2. Extracting the Uploaded Version ID

Capture the version ID output from `wrangler versions upload` for use in subsequent pipeline steps (traffic splits, notifications, rollback scripts).

```typescript
// scripts/upload-and-capture.ts
import { execSync } from 'child_process';

const tag     = `v${process.env.npm_package_version}-${process.env.GITHUB_SHA!.slice(0, 8)}`;
const message = `CI run #${process.env.GITHUB_RUN_NUMBER}`;

const output = execSync(
  `npx wrangler versions upload --tag "${tag}" --message "${message}" --json`,
  { encoding: 'utf8' }
);

interface VersionUploadResult {
  id: string;
  tag: string;
  number: number;
}

const result: VersionUploadResult = JSON.parse(output);
console.log(`Version ID: ${result.id}`);
console.log(`Version number: ${result.number}`);

// Write to a file for subsequent steps
import { writeFileSync } from 'fs';
writeFileSync('.version-id', result.id);
writeFileSync('.version-tag', result.tag);
```

---

## 3. Deploying a Specific Tagged Version

After upload, promote the tagged version to production. Using `--version-id` from the capture step ensures the exact artifact uploaded in this pipeline run receives traffic.

```typescript
// scripts/deploy-version.ts
import { execSync, readFileSync } from 'child_process';

const versionId = readFileSync('.version-id', 'utf8').trim();
const percent   = process.env.CANARY_PERCENT ?? '100';

execSync(
  `npx wrangler versions deploy ${versionId}@${percent}% --yes`,
  { stdio: 'inherit' }
);

console.log(`Deployed version ${versionId} at ${percent}% traffic`);
```

For a full canary split between an old and new version:

```bash
# Split traffic: 10% to new version, 90% stays on current
wrangler versions deploy <new-version-id>@10% <current-version-id>@90% --yes
```

---

## 4. Listing and Querying Version Metadata via API

Retrieve version history with tags programmatically for changelog generation or rollback selection.

```typescript
// scripts/list-versions.ts
const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const WORKER_NAME = process.env.WORKER_NAME!;
const API_TOKEN   = process.env.CF_API_TOKEN!;

interface WorkerVersion {
  id: string;
  number: number;
  metadata: { author_email: string; created_on: string; source: string };
  annotations: { 'workers/tag'?: string; 'workers/message'?: string };
}

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/versions?limit=10`,
  { headers: { Authorization: `Bearer ${API_TOKEN}` } }
);

const { result } = await res.json() as { result: WorkerVersion[] };

for (const v of result) {
  const tag     = v.annotations['workers/tag'] ?? '(untagged)';
  const message = v.annotations['workers/message'] ?? '';
  console.log(`[${v.number}] ${tag} — ${message} (${v.metadata.created_on})`);
}
```

---

## 5. Automated Rollback to Last Known-Good Tag

Use version metadata to find and redeploy the last version whose tag matches a stable naming convention.

```typescript
// scripts/rollback-to-stable.ts
const ACCOUNT_ID  = process.env.CF_ACCOUNT_ID!;
const WORKER_NAME = process.env.WORKER_NAME!;
const API_TOKEN   = process.env.CF_API_TOKEN!;
const STABLE_TAG_PREFIX = 'v';

interface WorkerVersion {
  id: string;
  number: number;
  annotations: { 'workers/tag'?: string };
}

const res = await fetch(
  `https://api.cloudflare.com/client/v4/accounts/${ACCOUNT_ID}/workers/scripts/${WORKER_NAME}/versions?limit=25`,
  { headers: { Authorization: `Bearer ${API_TOKEN}` } }
);

const { result } = await res.json() as { result: WorkerVersion[] };

// Skip the most recent (current broken version) and find the previous stable one
const stable = result.slice(1).find(
  (v) => v.annotations['workers/tag']?.startsWith(STABLE_TAG_PREFIX)
);

if (!stable) throw new Error('No stable version found for rollback');

const { execSync } = await import('child_process');
execSync(`npx wrangler versions deploy ${stable.id}@100% --yes`, { stdio: 'inherit' });
console.log(`Rolled back to version ${stable.id} (tag: ${stable.annotations['workers/tag']})`);
```

---

## Anti-Patterns

- **Deploying directly with `wrangler deploy`** — bypasses the version history; the upload and deployment steps are conflated, and metadata cannot be attached.
- **Using mutable tags** — tag values are immutable per upload but nothing prevents reusing the same string across uploads. Include the git SHA to make tags unique.
- **Not capturing the version ID in CI** — relying on `wrangler versions list` in a rollback script introduces a race condition if another deploy runs concurrently.
- **Omitting `--json` flag** — `wrangler versions upload` output format may change between wrangler releases; `--json` provides a stable machine-readable contract.

## Gotchas

- `wrangler versions upload` requires `workers_dev = false` in `wrangler.toml`; projects still using `workers_dev = true` must migrate to explicit routes or a Custom Domain before using the versioned deploy flow.
- The `--tag` value is stored in the `workers/tag` annotation key, not a top-level field. Queries via the REST API must read from `annotations['workers/tag']`.
- Version numbers are monotonically increasing integers per script but are not globally unique. Use the UUID `id` for all programmatic references.
- Traffic percentages in `wrangler versions deploy` must sum to exactly 100. Passing a single version without a percentage defaults to 100%.

## Verification

1. Run `wrangler versions list` immediately after upload; confirm the new version appears with the expected tag and message.
2. Verify traffic routing: `wrangler deployments list` should show the active deployment and the version IDs receiving traffic.
3. Confirm metadata via API: `GET /accounts/:id/workers/scripts/:name/versions/:version_id` and check the `annotations` field.
4. Test rollback script in staging: artificially set `CANARY_PERCENT=0` and confirm the previous stable version is selected.

## Related

- `worker-versioning-gradual-rollout.md`
- `canary-workers-gradual-traffic-split.md`
- `rollback-strategies-workers-pages.md`
- `workers-deployment-diff-changelog-automation.md`
- `deployment-audit-trail-provenance.md`

## Sources

- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- https://developers.cloudflare.com/workers/wrangler/commands/#versions
- https://developers.cloudflare.com/api/resources/workers/subresources/scripts/subresources/versions/
- https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/
