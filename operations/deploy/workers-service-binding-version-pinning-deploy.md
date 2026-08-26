# Workers Service Binding Version Pinning in Deploy

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A caller Worker and a callee Worker are deployed independently. A breaking change in the callee
rolls out before the caller has been updated to handle the new contract. Requests fail
mid-flight and the incident window lasts until the caller is also deployed or the callee is
rolled back. You need to pin the caller to a specific uploaded (but not yet fully promoted)
version of the callee during the deploy transition so both Workers ship together from the
consumer's perspective.

---

## Context

Workers Versions (the `wrangler versions upload` / `wrangler versions deploy` split-command
flow) let you separate "uploading a bundle" from "setting it live". A service binding between
two Workers resolves at the binding declaration level: by default the caller always reaches the
callee's live (latest promoted) version. The Workers Versions API adds a `version_id` field to
service-binding declarations so a caller can pin to an exact uploaded callee version,
effectively making the two Workers deploy atomically even though they live in separate projects.

Key concepts:
- `wrangler versions upload` — uploads a bundle and returns a `version_id`; sets NO traffic.
- `wrangler versions deploy` — assigns a traffic split to one or more versions.
- Service binding `version_id` — optional field that resolves the binding to an exact version
  instead of the live version. Requires the callee version to already be uploaded.

---

## 1. Upload the callee first, capture the version ID

```typescript
// scripts/upload-callee.ts
import { execSync } from "node:child_process";

interface WranglerVersionOutput {
  id: string;       // version_id
  number: number;
  metadata: { author_email: string; created_on: string };
}

function uploadVersion(workerDir: string): string {
  const raw = execSync("pnpm wrangler versions upload --json", {
    cwd: workerDir,
    env: {
      ...process.env,
      CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN!,
    },
    encoding: "utf-8",
  });

  const result: WranglerVersionOutput = JSON.parse(raw.trim());
  console.log(`Uploaded callee version: ${result.id}`);
  return result.id;
}

export const CALLEE_VERSION_ID = uploadVersion("packages/auth-worker");
```

---

## 2. Inject the version ID into the caller's wrangler config

```typescript
// scripts/patch-caller-config.ts
import { readFileSync, writeFileSync } from "node:fs";

interface ServiceBinding {
  binding: string;
  service: string;
  version_id?: string;
}

interface WranglerConfig {
  services?: ServiceBinding[];

}

function patchServiceBinding(
  configPath: string,
  bindingName: string,
  versionId: string
): void {
  // Use a TOML parser in production; simplified JSON example for clarity.
  // For TOML: use the `smol-toml` or `@iarna/toml` package.
  const raw = readFileSync(configPath, "utf-8");

  // Simple regex patch for the binding entry — replace with TOML lib in practice.
  const patched = raw.replace(
    /(\[services\][^\[]*?binding\s*=\s*"AUTH"[^\[]*?)/s,
    (match) => {
      if (match.includes("version_id")) {
        return match.replace(/version_id\s*=\s*"[^"]*"/, `version_id = "${versionId}"`);
      }
      return match.trimEnd() + `\nversion_id = "${versionId}"\n`;
    }
  );

  writeFileSync(configPath, patched, "utf-8");
  console.log(`Patched ${configPath}: AUTH binding → version ${versionId}`);
}

patchServiceBinding(
  "packages/api-worker/wrangler.toml",
  "AUTH",
  process.env.CALLEE_VERSION_ID!
);
```

Or manage config programmatically without mutating `wrangler.toml` on disk:

```typescript
// scripts/deploy-caller-pinned.ts
import { execSync } from "node:child_process";

function deployCaller(calleeVersionId: string): void {
  // Pass overrides via environment; callee version passed as a build-time constant.
  const env = {
    ...process.env,
    CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN!,
    // Custom env var read by the caller's wrangler.toml using vars substitution.
    AUTH_WORKER_VERSION: calleeVersionId,
  };

  execSync("pnpm wrangler versions upload --json", {
    cwd: "packages/api-worker",
    env,
    stdio: "inherit",
  });
}
```

---

## 3. Atomic version promotion

Upload both workers first, then promote both in sequence within the same CI job so the window
of version mismatch is as small as possible:

```typescript
// scripts/atomic-promote.ts
import { execSync } from "node:child_process";

interface VersionRef {
  versionId: string;
  percentage: number;
}

function promoteVersion(workerName: string, ref: VersionRef): void {
  execSync(
    `pnpm wrangler versions deploy ` +
      `--version-id ${ref.versionId} ` +
      `--percentage ${ref.percentage} ` +
      `--yes`,
    {
      env: {
        ...process.env,
        CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN!,
      },
      stdio: "inherit",
    }
  );
  console.log(
    `Promoted ${workerName}@${ref.versionId} at ${ref.percentage}% traffic.`
  );
}

// Step 1: upload both
const calleeVersionId = uploadVersion("packages/auth-worker");      // from §1
const callerVersionId = uploadCallerWithPin(calleeVersionId);        // from §2

// Step 2: promote callee, then immediately promote caller
// Total window of mismatch: time between the two promoteVersion calls (~seconds).
promoteVersion("auth-worker", { versionId: calleeVersionId, percentage: 100 });
promoteVersion("api-worker",  { versionId: callerVersionId, percentage: 100 });
```

---

## 4. Verifying the pinned binding is active

```typescript
// scripts/verify-version-binding.ts
async function getActiveVersionId(workerName: string): Promise<string> {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const token = process.env.CF_API_TOKEN!;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${workerName}/versions`,
    { headers: { Authorization: `Bearer ${token}` } }
  );

  const body = (await res.json()) as {
    result: Array<{ id: string; percentage: number }>;
  };

  const live = body.result.find((v) => v.percentage === 100);
  if (!live) throw new Error(`No 100% version found for ${workerName}`);
  return live.id;
}

async function verify(): Promise<void> {
  const calleeId = await getActiveVersionId("auth-worker");
  const callerId = await getActiveVersionId("api-worker");

  console.log(`callee live: ${calleeId}`);
  console.log(`caller live: ${callerId}`);

  // In a real assertion: parse the caller's binding config and confirm it pins calleeId.
  if (calleeId !== process.env.EXPECTED_CALLEE_VERSION) {
    throw new Error("Callee version mismatch after deploy");
  }
}

await verify();
```

---

## 5. Rolling back a pinned binding

If the caller must be rolled back, the `version_id` pin travels with it — the caller's previous
version already referenced the previous callee version, so rolling back the caller automatically
restores the correct binding pair:

```typescript
// scripts/rollback-caller.ts
async function getPreviousVersionId(workerName: string): Promise<string> {
  const accountId = process.env.CF_ACCOUNT_ID!;
  const token = process.env.CF_API_TOKEN!;

  const res = await fetch(
    `https://api.cloudflare.com/client/v4/accounts/${accountId}/workers/scripts/${workerName}/versions?per_page=2`,
    { headers: { Authorization: `Bearer ${token}` } }
  );
  const body = (await res.json()) as { result: Array<{ id: string }> };
  // [0] = current, [1] = previous
  return body.result[1]?.id ?? (() => { throw new Error("No previous version"); })();
}

const prevId = await getPreviousVersionId("api-worker");
execSync(`pnpm wrangler versions deploy --version-id ${prevId} --percentage 100 --yes`, {
  env: { ...process.env, CLOUDFLARE_API_TOKEN: process.env.CF_API_TOKEN! },
  stdio: "inherit",
});
```

---

## Anti-patterns

- **Pinning to a callee version that was never promoted**: if the callee version is only
  uploaded and the caller is promoted, but the callee promotion fails, the caller reaches an
  version that has never been independently validated. Always promote callee before caller.
- **Long-lived `version_id` pins**: a pin that persists across multiple releases means the
  caller accumulates staleness. Remove or update the pin with each release cycle.
- **Skipping `--yes` in CI**: `wrangler versions deploy` can prompt for confirmation interactively;
  always pass `--yes` in automated contexts to avoid hanging jobs.

---

## Gotchas

- `version_id` in service bindings requires both Workers to be on the same Cloudflare account.
  Cross-account service bindings do not support version pinning.
- A pinned `version_id` bypasses the callee's live traffic split. If the callee is running a
  canary (e.g., 10% on new version), the caller will always reach the pinned version, bypassing
  the canary logic entirely.
- `wrangler versions upload --json` output may include build log lines before the JSON object.
  Strip non-JSON lines with `raw.split('\n').filter(l => l.startsWith('{')).join('')` before
  `JSON.parse`.

---

## Verification

```bash
# Confirm binding resolves to pinned version
pnpm wrangler versions list --name api-worker
# Check that the live version was uploaded with the correct AUTH binding version_id

# Hit the deployed caller and confirm it routes to the expected callee version
curl https://api.example.com/whoami
# Response should reflect callee behavior at the pinned version, not live callee
```

---

## Related

- `workers-service-bindings-deployment-ordering.md`
- `workers-binding-version-management.md`
- `worker-versioning-gradual-rollout.md`
- `wrangler-versions-api-rollback-automation.md`

---

## Sources

- Workers Versions API (Gradual Deployments): https://developers.cloudflare.com/workers/configuration/versions-and-deployments/
- Service Bindings reference: https://developers.cloudflare.com/workers/runtime-apis/bindings/service-bindings/
- `wrangler versions` CLI docs: https://developers.cloudflare.com/workers/wrangler/commands/#versions
