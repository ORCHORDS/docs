# GPG-signed Git Tags as Wrangler Release Gates

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

Any developer with `wrangler deploy` permissions can ship to production at any commit by
running the command manually. The release pipeline needs a cryptographic gate: only commits
tagged with a verified GPG signature from a known key should trigger a production deploy.
Unsigned or lightweight tags — or signed tags from an unrecognized key — should abort the
pipeline before a single request reaches the Worker.

## Context

Git distinguishes three kinds of tags: lightweight (a plain ref), annotated (an object with
a message), and signed (an annotated tag whose message is wrapped in a GPG or SSH
signature). `git tag -s` creates a signed tag; `git verify-tag` checks it against the
keyring. GitHub Actions exposes tag refs in `GITHUB_REF` on `push` events with tag
patterns, letting you enforce signing in CI before calling `wrangler deploy`.

Wrangler v3 itself has no concept of tag verification — the gate must live in CI. The
pattern below composes `git verify-tag`, keyring management, and Wrangler environment
selection in a single Actions workflow.

## Generating and Publishing a Release Tag

```typescript
// scripts/tag-release.ts
// Wraps `git tag -s` to enforce the convention: vMAJOR.MINOR.PATCH[-env]
import { execSync } from "node:child_process";

type Environment = "staging" | "production";

interface ReleaseTagOptions {
  version: string;       // semver without "v", e.g. "1.4.2"
  environment: Environment;
  workerName: string;
  message?: string;
}

function validateSemver(version: string): void {
  if (!/^\d+\.\d+\.\d+$/.test(version)) {
    throw new Error(`Version must be semver (X.Y.Z), got: ${version}`);
  }
}

function createSignedTag(opts: ReleaseTagOptions): string {
  validateSemver(opts.version);
  const tag =
    opts.environment === "production"
      ? `v${opts.version}`
      : `v${opts.version}-${opts.environment}`;

  const message =
    opts.message ??
    `Release ${tag}\n\nWorker: ${opts.workerName}\nEnvironment: ${opts.environment}`;

  // -s = GPG sign using the committer key, -a = annotated
  execSync(`git tag -s "${tag}" -m ${JSON.stringify(message)}`, {
    stdio: "inherit",
  });

  execSync(`git push origin "${tag}"`, { stdio: "inherit" });
  console.log(`Pushed signed tag ${tag} to origin`);
  return tag;
}

// npx tsx scripts/tag-release.ts 1.4.2 production api-worker
const [, , version, environment, workerName] = process.argv;
createSignedTag({
  version,
  environment: environment as Environment,
  workerName,
});
```

## Verifying the Tag Signature in CI

```typescript
// scripts/verify-release-tag.ts
import { execSync, spawnSync } from "node:child_process";

const TRUSTED_FINGERPRINTS = (process.env.TRUSTED_GPG_FINGERPRINTS ?? "")
  .split(",")
  .map((f) => f.trim().replace(/\s/g, "").toUpperCase())
  .filter(Boolean);

function importTrustedKeys(): void {
  // Keys are stored as GitHub Actions secrets, one armored block per secret
  const keyEnvVars = Object.keys(process.env).filter((k) =>
    k.startsWith("GPG_RELEASE_KEY_")
  );
  for (const envVar of keyEnvVars) {
    const armored = process.env[envVar];
    if (!armored) continue;
    const result = spawnSync("gpg", ["--import"], {
      input: armored,
      encoding: "utf8",
    });
    if (result.status !== 0) {
      throw new Error(`Failed to import key from ${envVar}: ${result.stderr}`);
    }
  }
}

function verifyTagSignature(tag: string): void {
  const result = spawnSync("git", ["verify-tag", "--raw", tag], {
    encoding: "utf8",
  });

  if (result.status !== 0) {
    throw new Error(
      `Tag "${tag}" has no valid signature or signature is from untrusted key.\n${result.stderr}`
    );
  }

  // Parse the fingerprint from gpg --raw output
  const match = result.stderr.match(/VALIDSIG\s+([A-F0-9]{40})/);
  if (!match) {
    throw new Error(`Could not extract fingerprint from verify-tag output`);
  }

  const fingerprint = match[1].toUpperCase();
  if (TRUSTED_FINGERPRINTS.length > 0 && !TRUSTED_FINGERPRINTS.includes(fingerprint)) {
    throw new Error(
      `Tag signed by untrusted key ${fingerprint}.\nTrusted: ${TRUSTED_FINGERPRINTS.join(", ")}`
    );
  }

  console.log(`✓ Tag "${tag}" signed by trusted key ${fingerprint}`);
}

const tag = process.env.GITHUB_REF_NAME ?? process.argv[2];
if (!tag) throw new Error("No tag specified. Set GITHUB_REF_NAME or pass as argument.");

importTrustedKeys();
verifyTagSignature(tag);
```

## GitHub Actions Workflow: Signed-tag-gated Deploy

```yaml
# .github/workflows/wrangler-release.yml
name: Wrangler Release

on:
  push:
    tags:
      - "v[0-9]+.[0-9]+.[0-9]+"           # production: v1.4.2
      - "v[0-9]+.[0-9]+.[0-9]+-staging"    # staging:    v1.4.2-staging

jobs:
  verify-and-deploy:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # for Cloudflare OIDC if using token federation

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          fetch-tags: true

      - name: Install GnuPG
        run: sudo apt-get install -y gnupg

      - name: Verify signed tag
        run: npx tsx scripts/verify-release-tag.ts
        env:
          TRUSTED_GPG_FINGERPRINTS: ${{ vars.TRUSTED_GPG_FINGERPRINTS }}
          GPG_RELEASE_KEY_PLATFORM: ${{ secrets.GPG_RELEASE_KEY_PLATFORM }}
          GPG_RELEASE_KEY_INFRA: ${{ secrets.GPG_RELEASE_KEY_INFRA }}
          GITHUB_REF_NAME: ${{ github.ref_name }}

      - name: Determine environment from tag
        id: env
        run: |
          if [[ "${{ github.ref_name }}" == *"-staging" ]]; then
            echo "wrangler_env=staging" >> "$GITHUB_OUTPUT"
          else
            echo "wrangler_env=production" >> "$GITHUB_OUTPUT"
          fi

      - name: Install dependencies
        run: pnpm install --frozen-lockfile

      - name: Deploy Worker
        run: wrangler deploy --env ${{ steps.env.outputs.wrangler_env }}
        env:
          CLOUDFLARE_API_TOKEN: ${{ secrets.CF_API_TOKEN }}
```

## Keyring Management Helper

```typescript
// scripts/gpg-keyring.ts
// Rotate trusted keys stored as GitHub Actions variables
import { execSync } from "node:child_process";

function exportPublicKey(fingerprint: string): string {
  return execSync(`gpg --armor --export ${fingerprint}`).toString();
}

function listTrustedKeys(): void {
  const fps = (process.env.TRUSTED_GPG_FINGERPRINTS ?? "").split(",");
  for (const fp of fps) {
    const trimmed = fp.trim();
    if (!trimmed) continue;
    try {
      const info = execSync(`gpg --fingerprint ${trimmed} 2>/dev/null`).toString();
      console.log(info);
    } catch {
      console.warn(`Key ${trimmed} not found in local keyring`);
    }
  }
}

function verifyAllTagsOnBranch(branch = "main"): void {
  const tags = execSync(`git tag --merged ${branch}`).toString().trim().split("\n");
  for (const tag of tags.filter((t) => /^v\d+\.\d+\.\d+/.test(t))) {
    try {
      execSync(`git verify-tag ${tag} 2>/dev/null`);
      console.log(`OK  ${tag}`);
    } catch {
      console.warn(`FAIL ${tag} — unsigned or signature invalid`);
    }
  }
}

const cmd = process.argv[2];
if (cmd === "list") listTrustedKeys();
else if (cmd === "audit") verifyAllTagsOnBranch(process.argv[3]);
else if (cmd === "export") console.log(exportPublicKey(process.argv[3]));
```

## Anti-patterns

- **Lightweight tags as release gates**: `git tag v1.0.0` (without `-s` or `-a`) creates a
  ref only — it has no signature to verify. Always use `-s` (GPG-signed annotated tag) for
  gates.
- **A single shared signing key**: one compromised key unlocks all Workers. Issue one key
  per engineer and revoke individually. Store fingerprints in `TRUSTED_GPG_FINGERPRINTS` as
  a comma-separated list.
- **Skipping `--raw` in verify-tag**: `git verify-tag` exits 0 even for expired or revoked
  keys in some GPG configurations. Parse the `VALIDSIG` line from `--raw` output to be
  certain.

## Gotchas

- GitHub's tag protection rules can require signed tags at the push level, but they verify
  against GitHub's SSH signing, not the GPG keyring. The CI verification step above is still
  needed for GPG-specific fingerprint allowlisting.
- `GITHUB_REF_NAME` on a `push` event for a tag is the tag name without `refs/tags/` prefix
  — this is what the verification script expects.
- GPG key expiry silently breaks verification months after setup. Set a calendar reminder to
  rotate keys before they expire, or use no-expiry keys that you rotate manually on offboarding.

## Verification

```bash
# Create a test signed tag locally
git tag -s v0.0.0-test -m "test"
git verify-tag v0.0.0-test

# List tags with signature status on current branch
git tag --merged main | xargs -I{} git verify-tag {} 2>&1

# Run the audit helper
npx tsx scripts/gpg-keyring.ts audit main
```

## Related

- `git-tag-semantic-versioning-workers-deploy-gates.md`
- `gpg-ssh-commit-signing.md`
- `signed-commits-2026.md`
- `github-actions-wrangler-deploy-pipeline.md`
- `release-management-2026.md`

## Sources

- https://git-scm.com/docs/git-tag (--sign flag)
- https://git-scm.com/docs/git-verify-tag
- https://docs.github.com/en/repositories/releasing-projects-on-github/managing-releases-in-a-repository
- https://developers.cloudflare.com/workers/wrangler/commands/#deploy
