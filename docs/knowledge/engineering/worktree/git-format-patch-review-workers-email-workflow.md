# git format-patch: structured patch review for Cloudflare Workers email workflows

Date: 2026-08-23 / Author: example.com / Status: production

## Symptom / Use-case

A contributor working on a Cloudflare Workers project in an air-gapped environment, or a team practicing a strict asynchronous review process, needs to share changes without pushing a branch. Alternatively, a platform team wants to distribute hotfix patches to multiple downstream monorepo forks simultaneously. `git format-patch` produces self-contained, threaded-safe patch files that encode authorship, commit message, and diff in a single mbox-compatible unit—ready for email, pull request attachment, or programmatic application.

## Context

`git format-patch` is the export side of git's patch-based collaboration model; `git am` is the import side (covered in `git-am-mailbox-patch-application-workers.md`). Each patch file is an RFC 2822 email message with a diff payload. The patch numbering system (`[PATCH 1/3]`) supports ordered series. For Cloudflare Workers monorepos, the key use-cases are: distributing wrangler config changes to downstream forks, submitting changes to upstream open-source bindings, and creating reproducible review artifacts for compliance workflows.

## Generating a patch series from a feature branch

```bash
# Patches for the last 3 commits on the current branch
git format-patch HEAD~3

# Patches for commits not yet on main
git format-patch main

# Output to a directory instead of the current folder
git format-patch main --output-directory ./patches/auth-worker-refactor/

# Add a cover letter (introduces the series)
git format-patch main --cover-letter \
  --output-directory ./patches/auth-worker-refactor/

# Attach v2 prefix when revising after feedback
git format-patch main --reroll-count=2 \
  --output-directory ./patches/v2/auth-worker-refactor/
```

## TypeScript patch-bundle generator for Workers monorepos

```typescript
// scripts/generate-patch-bundle.ts
// Creates a dated, named patch bundle from a worktree branch.

import { execSync } from "node:child_process";
import { mkdirSync, writeFileSync, readdirSync } from "node:fs";
import { join } from "node:path";

interface PatchBundleOptions {
  /** Branch or commit range (e.g. "main..HEAD" or "HEAD~3") */
  range: string;
  /** Human-readable slug, becomes directory name */
  name: string;
  /** Optional version number for re-rolls */
  version?: number;
  /** Root of the monorepo */
  cwd?: string;
}

interface PatchBundleResult {
  directory: string;
  patches: string[];
  coverLetter: string | null;
}

export function generatePatchBundle(
  opts: PatchBundleOptions
): PatchBundleResult {
  const date = new Date().toISOString().slice(0, 10);
  const version = opts.version ? `v${opts.version}` : "v1";
  const dirName = `patches/${date}-${version}-${opts.name}`;
  const outDir = join(opts.cwd ?? process.cwd(), dirName);

  mkdirSync(outDir, { recursive: true });

  const rerollFlag =
    opts.version && opts.version > 1
      ? `--reroll-count=${opts.version}`
      : "";

  execSync(
    [
      "git format-patch",
      opts.range,
      "--cover-letter",
      "--thread",
      "--no-signature",
      rerollFlag,
      `--output-directory "${outDir}"`,
    ]
      .filter(Boolean)
      .join(" "),
    { cwd: opts.cwd ?? process.cwd(), stdio: "pipe" }
  );

  const files = readdirSync(outDir).sort();
  const coverLetter = files.find((f) => f.includes("cover-letter")) ?? null;
  const patches = files.filter((f) => f !== coverLetter);

  // Write a machine-readable manifest
  const manifest = {
    generated: new Date().toISOString(),
    range: opts.range,
    name: opts.name,
    version,
    coverLetter,
    patches,
  };
  writeFileSync(
    join(outDir, "MANIFEST.json"),
    JSON.stringify(manifest, null, 2)
  );

  return { directory: outDir, patches, coverLetter };
}

// CLI entry point
const [, , range, name, versionStr] = process.argv;
if (!range || !name) {
  console.error("Usage: tsx generate-patch-bundle.ts <range> <name> [version]");
  process.exit(1);
}
const result = generatePatchBundle({
  range,
  name,
  version: versionStr ? Number(versionStr) : undefined,
});
console.log(`Generated ${result.patches.length} patch(es) in ${result.directory}`);
if (result.coverLetter) {
  console.log(`Cover letter: ${result.coverLetter}`);
}
```

## Filling in the cover letter programmatically

```typescript
// scripts/fill-cover-letter.ts
// Replaces the template placeholders in the cover-letter patch.

import { readFileSync, writeFileSync } from "node:fs";

interface CoverLetterOptions {
  filePath: string;
  subject: string;
  body: string;
}

export function fillCoverLetter(opts: CoverLetterOptions): void {
  let content = readFileSync(opts.filePath, "utf8");

  // git format-patch emits these placeholder lines
  content = content.replace(
    /^Subject: \[.*?\] \*\*\* SUBJECT HERE \*\*\*$/m,
    `Subject: ${opts.subject}`
  );
  content = content.replace(
    /^\*\*\* BLURB HERE \*\*\*$/m,
    opts.body
  );

  writeFileSync(opts.filePath, content);
}

// Example usage in a release script:
fillCoverLetter({
  filePath: "patches/2026-08-23-v1-auth-worker/0000-cover-letter.patch",
  subject: "[PATCH 0/3] auth-worker: replace KV session store with D1",
  body: [
    "This series migrates the auth Worker's session storage from KV to D1,",
    "reducing read latency on cold cache by ~40ms (measured in staging).",
    "",
    "Changes are backward-compatible; existing KV keys are preserved for",
    "the 7-day grace period defined in the rollout plan.",
    "",
    "Tested against: Node 22, wrangler 3.x, miniflare 3.x.",
  ].join("\n"),
});
```

## Distributing patches via GitHub Actions artifact

```yaml
# .github/workflows/patch-bundle.yml
name: Generate Patch Bundle

on:
  workflow_dispatch:
    inputs:
      range:
        description: "Git range (e.g. main..HEAD)"
        required: true
        default: "main..HEAD"
      bundle_name:
        description: "Bundle slug (kebab-case)"
        required: true

jobs:
  bundle:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0   # Full history needed for format-patch

      - uses: pnpm/action-setup@v4

      - run: pnpm install --frozen-lockfile

      - name: Generate patch bundle
        run: |
          pnpm tsx scripts/generate-patch-bundle.ts \
            "${{ inputs.range }}" \
            "${{ inputs.bundle_name }}"

      - name: Upload patch bundle
        uses: actions/upload-artifact@v4
        with:
          name: "patch-bundle-${{ inputs.bundle_name }}"
          path: patches/
          retention-days: 30
```

## Applying a patch bundle for review (dry-run check)

```typescript
// scripts/check-patch-bundle.ts
// Validates that a patch bundle applies cleanly without actually committing.

import { execSync } from "node:child_process";
import { readdirSync } from "node:fs";
import { join } from "node:path";

function checkPatchBundle(bundleDir: string, cwd: string): void {
  const patches = readdirSync(bundleDir)
    .filter((f) => f.endsWith(".patch") && !f.includes("cover-letter"))
    .sort()
    .map((f) => join(bundleDir, f));

  if (patches.length === 0) {
    throw new Error(`No patch files found in ${bundleDir}`);
  }

  try {
    execSync(
      `git am --check --3way ${patches.map((p) => `"${p}"`).join(" ")}`,
      { cwd, stdio: "pipe" }
    );
    console.log(`All ${patches.length} patch(es) apply cleanly.`);
  } catch (err) {
    execSync("git am --abort", { cwd, stdio: "pipe" });
    const stderr = (err as { stderr: Buffer }).stderr?.toString() ?? "";
    throw new Error(`Patch apply check failed:\n${stderr}`);
  }
}

const [, , bundleDir] = process.argv;
checkPatchBundle(bundleDir ?? "./patches", process.cwd());
```

## Anti-patterns

- **Including generated lock files or build artifacts in patches** — they create noise, inflate patch size, and cause conflicts. Add `pnpm-lock.yaml` and `dist/` to the commit but strip them from patch series intended for upstream submission using `--ignore-if-in-upstream`.
- **Using patches as a substitute for pull requests in team workflows** — patches lose the review comment thread and CI status. Prefer PRs; use patches for air-gapped environments or upstream submission.
- **Numbering patches manually in subject lines** — let `git format-patch` handle `[PATCH N/M]` numbering. Manual numbering desynchronizes after re-rolls.
- **Forgetting `--thread` for multi-patch series** — email clients and patch trackers use `In-Reply-To` headers to thread the series; without `--thread` each patch appears as a standalone message.

## Gotchas

- `git format-patch` requires `fetch-depth: 0` in GitHub Actions; a shallow clone will fail to find the base commit in the range.
- Cover letter files are named `0000-cover-letter.patch`; their `[PATCH 0/N]` numbering means `git am` skips them automatically—but `git am --check` includes them unless you filter by filename.
- Binary files (WASM modules, compiled Worker bundles) cannot be represented in a standard patch; use `--binary` to include base85-encoded binary diffs, which inflates patch size.
- Re-rolls (`--reroll-count=2`) prefix subjects with `[PATCH v2 N/M]` but do not add `Supersedes` headers automatically; add those to the cover letter manually.
- Some email servers strip whitespace from patch lines, corrupting the diff. Send patches as plain-text attachments rather than inline body when emailing.

## Verification

```bash
# Generate and immediately check that the series applies cleanly
git format-patch main --output-directory /tmp/patches/
git am --check --3way /tmp/patches/*.patch
git am --abort  # clean up the dry-run state

# Inspect patch headers for correct threading
grep -E "^(From|Subject|In-Reply-To|References):" /tmp/patches/*.patch | head -30

# Validate the generated MANIFEST
pnpm tsx -e "
  import m from './patches/2026-08-23-v1-auth-worker/MANIFEST.json'
  assert(m.patches.length > 0, 'no patches');
  console.log('MANIFEST valid:', m.patches.length, 'patch(es)');
"
```

## Related

- `git-am-mailbox-patch-application-workers.md` — applying patch bundles
- `git-range-diff-review-after-rebase.md` — comparing patch series revisions
- `pr-review-process-2026.md` — standard PR review workflow
- `github-actions-wrangler-deploy-pipeline.md` — CI/CD integration
- `git-bundle-disaster-recovery-offline-clone.md` — full repo transport without a server

## Sources

- Git documentation: `git help format-patch`, `git help am`
- RFC 2822 (Internet Message Format) — the mbox format underlying patch files
- Git mailing list conventions: https://git-scm.com/docs/SubmittingPatches
- Cloudflare Workers: Wrangler CLI documentation (developers.cloudflare.com)
