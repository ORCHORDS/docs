# Wrangler Secret Bulk Import Script

- **Date:** 2026-08-23
- **Author:** example.com
- **Status:** production

## Symptom / Use-case

Projects with many Workers secrets — API keys, signing keys, database credentials — need a repeatable way to push secrets from a `.env` file or a secrets manager to Cloudflare without clicking through the dashboard. Wrangler's `secret put` command is interactive by default, making it unsuitable for CI pipelines or provisioning scripts that must set dozens of secrets non-interactively.

## Context

Wrangler supports `wrangler secret put <KEY> --env <env>` with the value piped via stdin, enabling scripted secret injection. For bulk operations a thin wrapper script reads a source of truth (a local `.env.secrets` file checked into a secure vault, a 1Password secret reference, or AWS Secrets Manager) and iterates over each key–value pair. The same script is used both locally for initial provisioning and in GitHub Actions for environment promotion.

## Bulk Import from a .env File

```typescript
// scripts/push-secrets.ts
// Usage: tsx scripts/push-secrets.ts --env production --file .env.secrets
import { execSync } from "node:child_process";
import { readFileSync, existsSync } from "node:fs";
import { parseArgs } from "node:util";

const { values } = parseArgs({
  args: process.argv.slice(2),
  options: {
    env: { type: "string", default: "production" },
    file: { type: "string", default: ".env.secrets" },
    worker: { type: "string" },
    "dry-run": { type: "boolean", default: false },
  },
});

const { env, file, worker, "dry-run": dryRun } = values;

if (!existsSync(file!)) {
  console.error(`Secrets file not found: ${file}`);
  process.exit(1);
}

const raw = readFileSync(file!, "utf-8");

// Parse KEY=VALUE lines; skip comments and blank lines
const pairs: Array<[string, string]> = raw
  .split("\n")
  .map((line) => line.trim())
  .filter((line) => line && !line.startsWith("#"))
  .map((line) => {
    const eq = line.indexOf("=");
    if (eq === -1) throw new Error(`Invalid line: ${line}`);
    const key = line.slice(0, eq).trim();
    // Remove surrounding quotes from value
    const rawVal = line.slice(eq + 1).trim();
    const value = rawVal.replace(/^["']|["']$/g, "");
    return [key, value] as [string, string];
  });

const workerFlag = worker ? `--name ${worker}` : "";

let succeeded = 0;
let failed = 0;

for (const [key, value] of pairs) {
  const cmd = `wrangler secret put ${key} --env ${env} ${workerFlag}`.trim();

  if (dryRun) {
    console.log(`[DRY RUN] Would set: ${key}`);
    continue;
  }

  try {
    execSync(cmd, {
      input: value,
      stdio: ["pipe", "inherit", "inherit"],
      encoding: "utf-8",
    });
    console.log(`  set ${key}`);
    succeeded++;
  } catch {
    console.error(`  FAILED ${key}`);
    failed++;
  }
}

console.log(`\nDone: ${succeeded} set, ${failed} failed.`);
if (failed > 0) process.exit(1);
```

## Bulk Import from 1Password CLI

```typescript
// scripts/push-secrets-op.ts
// Pulls secrets from a 1Password vault item and pushes them to Cloudflare.
// Requires: op CLI authenticated, CLOUDFLARE_API_TOKEN set.
import { execSync } from "node:child_process";

const VAULT = "Engineering";
const ITEM = "workers-production-secrets";
const CF_ENV = "production";

interface OPField {
  id: string;
  label: string;
  value?: string;
  type: string;
}

// Retrieve all fields from the 1Password item as JSON
const raw = execSync(`op item get "${ITEM}" --vault "${VAULT}" --format json`, {
  encoding: "utf-8",
});

const item: { fields: OPField[] } = JSON.parse(raw);

// Only push fields that have a non-empty value
const secrets = item.fields.filter(
  (f) => f.type !== "OTP" && f.value && f.value.trim()
);

for (const field of secrets) {
  const key = field.label.toUpperCase().replace(/[^A-Z0-9_]/g, "_");
  const value = field.value!;

  execSync(`wrangler secret put ${key} --env ${CF_ENV}`, {
    input: value,
    stdio: ["pipe", "inherit", "inherit"],
    encoding: "utf-8",
  });

  console.log(`  set ${key}`);
}
```

## GitHub Actions CI Workflow

```yaml
# .github/workflows/deploy-secrets.yml
name: Push Secrets to Cloudflare

on:
  workflow_dispatch:
    inputs:
      environment:
        description: "Target environment"
        required: true
        default: "production"
        type: choice
        options: [staging, production]

jobs:
  push-secrets:
    runs-on: ubuntu-latest
    environment: ${{ inputs.environment }}
    steps:
      - uses: actions/checkout@v4

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - name: Write secrets file from GitHub environment secrets
        run: |
          cat > .env.secrets << 'EOF'
          API_KEY=${{ secrets.API_KEY }}
          SIGNING_SECRET=${{ secrets.SIGNING_SECRET }}
          DB_URL=${{ secrets.DB_URL }}
          EOF

      - name: Push secrets to Cloudflare
        run: pnpm tsx scripts/push-secrets.ts --env ${{ inputs.environment }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}

      - name: Cleanup
        if: always()
        run: rm -f .env.secrets
```

## Anti-patterns

- Committing a `.env.secrets` file to the repository, even temporarily — use `.gitignore` to exclude all `*.secrets` and `*.env` files and confirm with `git status` before every commit.
- Using `wrangler secret bulk` with a JSON file written to disk in CI — the file containing plaintext secrets persists on the runner until the job finishes; prefer piping via stdin as shown above.
- Setting secrets without scoping to `--env` — in multi-environment Workers projects this silently sets the secret on the `production` environment (Wrangler's default), overwriting live credentials during staging operations.

## Gotchas

- `wrangler secret put` reads the secret value from stdin and trims a trailing newline. Shell `echo "value"` adds a newline that Wrangler strips correctly, but binary secrets (base64-encoded keys) must be passed exactly — use `printf '%s'` instead of `echo` when constructing the shell command.
- When running the bulk script inside a Turborepo or pnpm workspace pipeline, `CLOUDFLARE_API_TOKEN` must be in the environment — Wrangler does not read it from `.env` automatically in non-interactive mode.
- `wrangler secret list --env production` returns only secret names, never values. After a bulk push, verify by listing and confirming all expected keys appear.

## Verification

```bash
# Dry-run to verify parsing without pushing anything
pnpm tsx scripts/push-secrets.ts --dry-run --file .env.secrets.example

# Push to staging only
pnpm tsx scripts/push-secrets.ts --env staging

# Confirm all secrets were set
wrangler secret list --env production

# Remove a single secret
wrangler secret delete OLD_KEY --env production
```

## Related

- `devtools/wrangler-dev-local-d1-r2-kv.md`
- `devtools/dotenv-local-setup.md`
- `devtools/direnv-env-setup.md`

## Sources

- https://developers.cloudflare.com/workers/wrangler/commands/#secret
- https://developer.1password.com/docs/cli/reference/management-commands/item/
- https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions
