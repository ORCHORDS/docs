# Wrangler Version Rollback with Git Tag Workflow

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

You deployed a new Workers version that introduced a latency regression and you need to revert production within sixty seconds. You have no pre-baked rollback script, so you are manually running `wrangler rollback` and hoping the previous version is still stored in Cloudflare's version history. Meanwhile, your git tags are out of sync: the tag `v1.4.2` points to the commit that was deployed before the bad push, but you have no automated link between that tag and the Wrangler version ID that was live at `v1.4.2`.

The goal is a deterministic, auditable rollback process where every git tag corresponds to an exact Cloudflare Workers version UUID, making it possible to roll back to any tagged release by version ID — not just "the previous deployment."

---

## Context

Cloudflare Workers separates the concepts of **version** (an immutable bundle uploaded via `wrangler versions upload`) and **deployment** (a traffic assignment that points at one or more versions via `wrangler deployments create` or `wrangler deploy`). This split, introduced as part of the Workers Gradual Deployments feature, makes it possible to roll traffic back to a specific version UUID without re-uploading code.

`wrangler rollback` reverts to the previous _deployment_, not the previous _version_. If you deployed version A, then version B, then version A again, `wrangler rollback` from B would go to A — but it does not let you target an arbitrary version from three releases ago.

The pattern below stores the Wrangler version ID in git tag metadata at deploy time. A rollback then becomes a three-step process:

1. `git show` the tag to retrieve the stored version UUID.
2. `wrangler deployments create --version-id <uuid>` to promote that version to 100% traffic.
3. Push a `rollback/v<X.Y.Z>` git tag to record the event.

---

## Deploy Pipeline: Tagging with Version UUID

```typescript
// scripts/deploy-and-tag.ts
import { execSync } from "node:child_process";
import { readFileSync } from "node:fs";

interface VersionUploadResult {
  id: string;
  number: number;
  metadata: { created_on: string };
}

interface DeployResult {
  id: string;
  versions: Array<{ version_id: string; percentage: number }>;
}

function run(cmd: string, opts?: { cwd?: string }): string {
  return execSync(cmd, { encoding: "utf-8", ...opts }).trim();
}

const packageJson = JSON.parse(readFileSync("package.json", "utf-8")) as {
  version: string;
  name: string;
};
const semver = packageJson.version;
const workerName = packageJson.name.replace("@repo/", "");
const gitSha = run("git rev-parse HEAD");
const gitBranch = run("git rev-parse --abbrev-ref HEAD");

// Step 1: Upload a new version (does not affect traffic)
const uploadRaw = run(
  `wrangler versions upload --name ${workerName} --message "v${semver} ${gitSha}" --json`
);
const upload = JSON.parse(uploadRaw) as VersionUploadResult;
const versionId = upload.id;

console.log(`Uploaded version ${versionId} for v${semver}`);

// Step 2: Deploy the version to 100% traffic
const deployRaw = run(
  `wrangler deployments create --version-id ${versionId} --version-percentage 100 --json`
);
const deploy = JSON.parse(deployRaw) as DeployResult;

console.log(`Deployed: ${deploy.id}`);

// Step 3: Tag the commit with the Wrangler version UUID in tag metadata
const tagName = `v${semver}`;
const tagMessage = [
  `Release ${tagName}`,
  ``,
  `wrangler-version-id: ${versionId}`,
  `wrangler-deployment-id: ${deploy.id}`,
  `worker-name: ${workerName}`,
  `git-sha: ${gitSha}`,
  `deployed-at: ${new Date().toISOString()}`,
].join("\n");

// Create an annotated tag with the metadata in the message
run(`git tag -a "${tagName}" -m "${tagMessage}"`);
run(`git push origin "${tagName}"`);

console.log(`Tagged ${tagName} with version ID ${versionId}`);
```

---

## Rollback Script

```typescript
// scripts/rollback.ts
import { execSync } from "node:child_process";

function run(cmd: string): string {
  return execSync(cmd, { encoding: "utf-8" }).trim();
}

const targetTag = process.argv[2];

if (!targetTag) {
  console.error("Usage: npx tsx scripts/rollback.ts <tag>");
  console.error("Example: npx tsx scripts/rollback.ts v1.4.2");
  process.exit(1);
}

// Step 1: Retrieve the tag message and parse the version UUID
const tagMessage = run(`git tag -l "${targetTag}" -n99`);
const versionIdMatch = tagMessage.match(/wrangler-version-id:\s*([a-f0-9-]{36})/);
const workerNameMatch = tagMessage.match(/worker-name:\s*(\S+)/);

if (!versionIdMatch || !workerNameMatch) {
  console.error(`Tag ${targetTag} does not contain Wrangler metadata.`);
  console.error("Was it created with the deploy-and-tag script?");
  process.exit(1);
}

const versionId = versionIdMatch[1];
const workerName = workerNameMatch[1];

console.log(`Rolling back ${workerName} to version ${versionId} (tag ${targetTag})`);

// Step 2: Confirm before applying
if (process.env.CI !== "true") {
  const { createInterface } = await import("node:readline");
  const rl = createInterface({ input: process.stdin, output: process.stdout });
  const confirmed = await new Promise<boolean>((resolve) => {
    rl.question("Proceed? [y/N] ", (answer) => {
      rl.close();
      resolve(answer.toLowerCase() === "y");
    });
  });
  if (!confirmed) {
    console.log("Rollback cancelled.");
    process.exit(0);
  }
}

// Step 3: Deploy the specific version to 100% traffic
run(
  `wrangler deployments create --version-id ${versionId} --version-percentage 100`
);

console.log(`Rollback complete. ${workerName} is now serving ${targetTag} (${versionId})`);

// Step 4: Record the rollback event as a git tag
const rollbackTag = `rollback/${targetTag}-${Date.now()}`;
run(
  `git tag -a "${rollbackTag}" HEAD -m "Rollback to ${targetTag}\n\nwrangler-version-id: ${versionId}\nrolled-back-at: ${new Date().toISOString()}"`
);
run(`git push origin "${rollbackTag}"`);

console.log(`Recorded rollback event as tag ${rollbackTag}`);
```

Usage:

```bash
# Roll back to the version that was deployed at v1.4.2
npx tsx scripts/rollback.ts v1.4.2

# In CI (no confirmation prompt)
CI=true npx tsx scripts/rollback.ts v1.4.2
```

---

## GitHub Actions: Deploy with Tag

```yaml
# .github/workflows/release.yml
name: Release and Deploy

on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"

jobs:
  deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: write  # needed to push the annotated tag
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Build
        run: pnpm build

      - name: Deploy and tag version UUID
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          GIT_AUTHOR_NAME: github-actions[bot]
          GIT_AUTHOR_EMAIL: github-actions[bot]@users.noreply.github.com
          GIT_COMMITTER_NAME: github-actions[bot]
          GIT_COMMITTER_EMAIL: github-actions[bot]@users.noreply.github.com
        run: npx tsx scripts/deploy-and-tag.ts
```

---

## GitHub Actions: Rollback Dispatch

```yaml
# .github/workflows/rollback.yml
name: Rollback Worker

on:
  workflow_dispatch:
    inputs:
      target_tag:
        description: "Git tag to roll back to (e.g. v1.4.2)"
        required: true
        type: string

jobs:
  rollback:
    runs-on: ubuntu-latest
    environment: production  # requires approval in GitHub environment settings
    permissions:
      contents: write
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - uses: pnpm/action-setup@v4
      - uses: actions/setup-node@v4
        with:
          node-version: 22
          cache: pnpm

      - run: pnpm install --frozen-lockfile

      - name: Rollback to ${{ inputs.target_tag }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          CI: "true"
          GIT_AUTHOR_NAME: github-actions[bot]
          GIT_AUTHOR_EMAIL: github-actions[bot]@users.noreply.github.com
          GIT_COMMITTER_NAME: github-actions[bot]
          GIT_COMMITTER_EMAIL: github-actions[bot]@users.noreply.github.com
        run: npx tsx scripts/rollback.ts "${{ inputs.target_tag }}"
```

---

## Listing Available Rollback Targets

```bash
# Show all release tags with their stored version UUIDs
git tag --sort=-creatordate \
  | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
  | head -20 \
  | while read tag; do
      uuid=$(git tag -l "$tag" -n99 | grep 'wrangler-version-id' | awk '{print $2}')
      echo "$tag  →  $uuid"
    done
```

---

## Anti-patterns

- **Using lightweight (non-annotated) tags** — Lightweight tags do not carry a message, so there is nowhere to store the version UUID. Always use `git tag -a`.
- **Relying solely on `wrangler rollback`** — This reverts to the previous deployment, not to a specific historical version. If you deployed A → B → rollback → A → C, running `wrangler rollback` from C goes back to A's second deployment, which is correct — but the identity of that deployment is ambiguous without the UUID.
- **Storing the version UUID only in CI logs** — CI logs expire. Annotated git tags are permanent (until explicitly deleted) and live in the repository.
- **Pushing the tag before confirming the deployment succeeded** — Tag on success, not before. If `wrangler deployments create` fails, you should not have a tag pointing at a non-live version.
- **Embedding secrets in tag messages** — Tag messages are pushed to the remote and visible to all repository collaborators. Store only non-sensitive identifiers (version UUIDs, deployment IDs).

---

## Gotchas

- `wrangler versions upload` and `wrangler deployments create` are available starting from Wrangler v3.40.0. Earlier versions only have `wrangler deploy` which uploads and deploys atomically, making it impossible to deploy a previously uploaded version.
- `wrangler deployments create` requires the `Workers Scripts: Edit` and `Account Settings: Read` API token permissions. The older `CLOUDFLARE_API_TOKEN` used only for `wrangler deploy` may not have `deployments create` rights — audit before rollback.
- Annotated tags are not fetched by `git fetch` by default. CI checkouts that use `--filter=blob:none` or `--depth=1` may not have the tag metadata. Use `git fetch --tags` or `actions/checkout@v4` with `fetch-depth: 0`.
- `wrangler deployments create` with `--version-percentage 100` is a hard traffic cut. For a graduated rollback (route 10% traffic first) omit the flag and use Gradual Deployments instead — see the Cloudflare docs.

---

## Verification

```bash
# Confirm a tag has version metadata
git show v1.4.2 | grep -E 'wrangler-(version|deployment)-id'

# Confirm the version exists in Cloudflare's history
WORKER_NAME=my-worker
wrangler versions list --name "$WORKER_NAME" | grep <uuid-from-tag>

# Dry-run rollback without applying
git tag -l "v1.4.2" -n99

# Post-rollback: confirm traffic is on the expected version
wrangler deployments list --name "$WORKER_NAME" | head -5
```

---

## Related

- `wrangler-version-upload-deploy-split-workflow.md`
- `git-tag-semantic-versioning-workers-deploy-gates.md`
- `git-tag-signed-gpg-wrangler-release-pipeline.md`
- `git-revert-safe-rollback-workers-production.md`
- `canary-deployment-strategy.md`
- `github-actions-reusable-2026.md`

---

## Sources

- Cloudflare Docs — [Gradual deployments](https://developers.cloudflare.com/workers/configuration/versions-and-deployments/gradual-deployments/)
- Cloudflare Docs — [wrangler versions](https://developers.cloudflare.com/workers/wrangler/commands/#versions)
- Cloudflare Docs — [wrangler deployments](https://developers.cloudflare.com/workers/wrangler/commands/#deployments)
- Git SCM — [git-tag(1)](https://git-scm.com/docs/git-tag)
