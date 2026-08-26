# git notes: Deployment Metadata for Cloudflare Workers Versions

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Your CI pipeline deploys a Cloudflare Worker and records the Wrangler version ID in a log
file that scrolls off in a week. Six weeks later, a performance regression is tracked to a
specific commit, but no one can quickly answer "which Worker version ID was live at that
commit?" or "what environment URL did this SHA deploy to?" `git notes` solves this without
touching the commit graph — metadata attaches to commits after the fact and travels with the
repo.

## Context

`git notes` stores arbitrary blobs in refs under `refs/notes/`. The most common namespace is
`refs/notes/commits`, but you can create parallel namespaces — one per environment, one per
deployment type — all keyed to the same commit SHA. Notes are not part of the commit object,
so they never change the SHA; they can be added, amended, or removed without rewriting
history. The catch is that `git fetch` and `git push` do not transfer notes by default: you
must add explicit refspecs to your remote configuration and CI fetch/push steps.

Wrangler v3+ surfaces a stable `versionId` in `wrangler deploy --json` output. That UUID is
the bridge between a git commit and the Cloudflare dashboard's "Deployments" tab.

## Attaching a Wrangler Version ID to a Commit

```typescript
// scripts/record-deployment-note.ts
import { execSync } from "node:child_process";

interface WranglerDeployOutput {
  versionId: string;
  deploymentId: string;
  workerName: string;
  environment: string;
  url: string;
  timestamp: string;
}

function recordDeploymentNote(
  sha: string,
  output: WranglerDeployOutput,
  namespace: string = "deployments"
): void {
  const note = [
    `wrangler-version-id: ${output.versionId}`,
    `deployment-id:       ${output.deploymentId}`,
    `worker:              ${output.workerName}`,
    `environment:         ${output.environment}`,
    `url:                 ${output.url}`,
    `deployed-at:         ${output.timestamp}`,
    `deployed-by:         ${process.env.GITHUB_ACTOR ?? "ci"}`,
  ].join("\n");

  execSync(
    `git notes --ref=${namespace} add -f -m ${JSON.stringify(note)} ${sha}`,
    { stdio: "pipe" }
  );
}

// Called from CI after wrangler deploy --json > deploy.json
const raw = require("fs").readFileSync("deploy.json", "utf8");
const deployOutput: WranglerDeployOutput = JSON.parse(raw);
const sha = execSync("git rev-parse HEAD").toString().trim();

recordDeploymentNote(sha, deployOutput, "deployments/production");
```

## Pushing and Fetching Notes in CI

Without explicit refspecs, notes never leave the local repo. Add these to every CI job that
reads or writes deployment notes:

```yaml
# .github/workflows/deploy-workers.yml
jobs:
  deploy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # full history required for notes to attach correctly

      - name: Fetch existing deployment notes
        run: |
          git fetch origin 'refs/notes/deployments/production:refs/notes/deployments/production' || true
          git fetch origin 'refs/notes/deployments/staging:refs/notes/deployments/staging' || true

      - name: Deploy Worker
        run: wrangler deploy --env production --json > deploy.json
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}

      - name: Record deployment note
        run: npx tsx scripts/record-deployment-note.ts

      - name: Push deployment notes
        run: |
          git push origin 'refs/notes/deployments/production:refs/notes/deployments/production'
```

## Querying Notes for a Commit Range

```typescript
// scripts/query-deployment-notes.ts
import { execSync } from "node:child_process";

interface DeploymentRecord {
  sha: string;
  versionId: string | null;
  environment: string | null;
  url: string | null;
  deployedAt: string | null;
}

function parseNote(raw: string): Record<string, string> {
  return Object.fromEntries(
    raw
      .split("\n")
      .filter(Boolean)
      .map((line) => {
        const [key, ...rest] = line.split(":");
        return [key.trim(), rest.join(":").trim()];
      })
  );
}

function deploymentsInRange(
  from: string,
  to: string,
  namespace = "deployments/production"
): DeploymentRecord[] {
  const shas = execSync(`git log --format=%H ${from}..${to}`)
    .toString()
    .trim()
    .split("\n")
    .filter(Boolean);

  return shas.map((sha) => {
    try {
      const raw = execSync(
        `git notes --ref=${namespace} show ${sha} 2>/dev/null`
      ).toString();
      const parsed = parseNote(raw);
      return {
        sha: sha.slice(0, 8),
        versionId: parsed["wrangler-version-id"] ?? null,
        environment: parsed["environment"] ?? null,
        url: parsed["url"] ?? null,
        deployedAt: parsed["deployed-at"] ?? null,
      };
    } catch {
      return { sha: sha.slice(0, 8), versionId: null, environment: null, url: null, deployedAt: null };
    }
  });
}

// Usage: find which commits in a range were deployed and their version IDs
const records = deploymentsInRange("v1.4.0", "v1.5.0");
const deployed = records.filter((r) => r.versionId !== null);
console.table(deployed);
```

## Configuring Global Fetch/Push of Notes

To avoid per-repo boilerplate, add a global fetch refspec once:

```bash
# In your project .git/config (or global ~/.gitconfig for all repos)
[remote "origin"]
    fetch = +refs/notes/deployments/*:refs/notes/deployments/*
    push  = refs/notes/deployments/*:refs/notes/deployments/*
```

In TypeScript tooling you can write this programmatically during repo setup:

```typescript
import { execSync } from "node:child_process";

function configureNotesRefspecs(namespace = "deployments"): void {
  const fetchRefspec = `+refs/notes/${namespace}/*:refs/notes/${namespace}/*`;
  const pushRefspec  = `refs/notes/${namespace}/*:refs/notes/${namespace}/*`;

  // Idempotent — git config --add allows duplicates, so check first
  const existing = execSync("git config --get-all remote.origin.fetch")
    .toString();

  if (!existing.includes(fetchRefspec)) {
    execSync(`git config --add remote.origin.fetch "${fetchRefspec}"`);
  }
  const pushExisting = execSync(
    "git config --get-all remote.origin.push 2>/dev/null || true"
  ).toString();
  if (!pushExisting.includes(pushRefspec)) {
    execSync(`git config --add remote.origin.push "${pushRefspec}"`);
  }
}
```

## Anti-patterns

- **Storing notes in refs/notes/commits**: the default namespace collides with any other tool
  (IDEs, bots) that also writes to it. Always use a scoped namespace like
  `deployments/production`.
- **Forgetting `--force` on re-deploy**: a second deploy to the same commit without `-f`
  fails silently on some git versions. Use `add -f` (force-overwrite) consistently.
- **Attaching notes to merge commits only**: notes on merge SHAs are useful but lose
  granularity. Attach to the HEAD of the branch being deployed for precise blame mapping.

## Gotchas

- Notes are rebased-away: if you rebase a branch after attaching notes, the new commit SHAs
  are different and the old notes orphan under the old SHAs. Always attach notes post-merge,
  never pre-rebase.
- `git log --notes` shows notes inline but only for the default `refs/notes/commits`
  namespace. For custom namespaces: `git log --notes=deployments/production`.
- GitHub's web UI does not render git notes. Notes are a CLI/API artefact only.

## Verification

```bash
# Confirm a note was attached
git notes --ref=deployments/production show HEAD

# List all noted commits in a range
git log --notes=deployments/production --format="%H %N" v1.4.0..HEAD \
  | grep wrangler-version-id

# Confirm notes were pushed to origin
git ls-remote origin 'refs/notes/deployments/*'
```

## Related

- `git-log-follow-file-history-workers.md`
- `git-describe-version-string-workers-ci.md`
- `git-tag-semantic-versioning-workers-deploy-gates.md`
- `wrangler-environments-staging-production.md`
- `github-actions-wrangler-deploy-pipeline.md`

## Sources

- https://git-scm.com/docs/git-notes
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
- https://git-scm.com/docs/gitrepository-layout (refs/notes layout)
