# pnpm patch for Dependency Hotfixes

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A third-party dependency has a bug that blocks your release, but the upstream fix hasn't been
published to npm yet. You can see the fix in the upstream repository — a one-line change — but
the maintainer hasn't cut a new version. You need to ship in hours, not days. Forking the package,
publishing a fork, and updating lockfiles is a multi-step detour.

`pnpm patch` lets you apply local edits directly to a package in your `node_modules`, commit the
diff as a patch file, and have pnpm reapply it automatically on every subsequent install.

## Context

`pnpm patch` was introduced in pnpm 7.4 (2022) and is modelled on the `patch-package` npm
package but implemented natively in pnpm. The workflow creates a copy of the target package in a
temporary directory, lets you edit it, then calls `pnpm patch-commit` to write a `.patch` file
and register it in `pnpm.patchedDependencies` inside `pnpm-lock.yaml`.

The patch is re-applied on:
- `pnpm install`
- `pnpm update`
- CI installs (as long as the lockfile is committed)

The feature is stable as of pnpm 8+ and is first-class — no extra dependencies required.

## Step-by-Step Workflow

### 1. Start the patch session

```bash
pnpm patch <package-name>@<version>
```

Example:

```bash
pnpm patch some-library@3.2.1
```

pnpm creates a temporary directory, copies the package contents into it, and prints the path:

```
You can now edit the following folder: /tmp/pnpm-patch-some-library/
Once you're done with your changes, run:
  pnpm patch-commit '/tmp/pnpm-patch-some-library/'
```

### 2. Edit the temporary copy

Open the printed path and make your changes:

```bash
# Open the temp directory in your editor
code /tmp/pnpm-patch-some-library/

# Or make a targeted edit with sed / your editor of choice
nano /tmp/pnpm-patch-some-library/dist/index.js
```

The edits can touch any files in the package — compiled JS, type definitions, CSS, etc.

### 3. Commit the patch

```bash
pnpm patch-commit '/tmp/pnpm-patch-some-library/'
```

pnpm diffs the modified temp directory against the original package and writes a `.patch` file:

```
patches/some-library@3.2.1.patch
```

It also updates `package.json`:

```json
{
  "pnpm": {
    "patchedDependencies": {
      "some-library@3.2.1": "patches/some-library@3.2.1.patch"
    }
  }
}
```

And records the patch in `pnpm-lock.yaml`. Commit both files.

### 4. Verify the patch applies cleanly

```bash
pnpm install
# pnpm applies the patch automatically after installing
```

Output during install:

```
. preparations: applying patches...
  some-library@3.2.1: patch applied
```

## Patch File Format

The `.patch` file is a standard unified diff and is human-readable:

```diff
diff --git a/dist/index.js b/dist/index.js
index abc123..def456 100644
--- a/dist/index.js
+++ b/dist/index.js
@@ -42,7 +42,7 @@ function someFunction(input) {
-  if (input === null) throw new Error('unexpected null');
+  if (input == null) throw new Error('unexpected null or undefined');
   return process(input);
 }
```

You can hand-edit the `.patch` file later if the temporary-directory flow is inconvenient.

## Patching a Scoped Package

```bash
pnpm patch @scope/package@1.0.0
pnpm patch-commit '/tmp/pnpm-patch-@scope-package/'
```

The lockfile key uses the scoped name with `@` intact:

```json
{
  "pnpm": {
    "patchedDependencies": {
      "@scope/package@1.0.0": "patches/@scope__package@1.0.0.patch"
    }
  }
}
```

Note: the filename on disk replaces `/` with `__` for filesystem compatibility.

## Workspace (Monorepo) Considerations

Patches registered in the workspace root `package.json` apply globally — to every workspace
package that depends on the patched version. You cannot currently scope a patch to a single
workspace package in the `patchedDependencies` declaration.

If workspace package A depends on `lib@1.0.0` and package B depends on `lib@2.0.0` and you
need to patch only `1.0.0`, pnpm will only apply the patch to the `lib@1.0.0` instances, which
is the expected behaviour given the version pinning in the key.

## Updating the Patch After an Upstream Release

When the upstream releases a fixed version, remove the patch:

1. Delete the `.patch` file from `patches/`.
2. Remove the entry from `pnpm.patchedDependencies` in `package.json`.
3. Update the dependency version: `pnpm update some-library`.
4. Verify the fix is present in the new version.
5. Commit the removal.

Leaving stale patches in place is a common source of confusion. Add a comment or a TODO in
the patch file header with the upstream issue URL and the target version to remove the patch.

## Applying a Patch from a GitHub PR Diff

Sometimes you want to apply an upstream PR diff rather than writing the patch manually:

```bash
# Download the GitHub PR diff
curl -L https://github.com/owner/repo/pull/123.diff -o /tmp/upstream.diff

# Start the patch session
pnpm patch some-library@3.2.1

# Apply the upstream diff to the temp directory
cd /tmp/pnpm-patch-some-library/
patch -p1 < /tmp/upstream.diff

# Commit
pnpm patch-commit '/tmp/pnpm-patch-some-library/'
```

Inspect the resulting `.patch` file carefully — the upstream PR may touch files outside the
published npm package (tests, docs) that don't exist in `node_modules`; `patch` will warn about
these with "No such file" messages that you can ignore.

## CI Verification

Ensure CI verifies patches apply cleanly and that tests still pass with the patched dependency:

```yaml
# .github/workflows/ci.yml
- name: Install dependencies
  run: pnpm install --frozen-lockfile
  # pnpm applies registered patches automatically during install

- name: Verify patch list
  run: |
    cat package.json | jq '.pnpm.patchedDependencies'
```

A `--frozen-lockfile` install will fail if the lockfile is out of sync with `patchedDependencies`,
giving you an early signal if someone removed the lockfile entry without removing the patch file.

## Anti-patterns

**Patching compiled/minified output and skipping source** — if the package ships both source and
compiled output, patch the source where possible. Patching only the minified bundle makes diffs
unreadable and the patch fragile across minor versions.

**Patching `node_modules` directly without `pnpm patch`** — manual edits to `node_modules` are
destroyed on the next `pnpm install`. Always use the `pnpm patch` → `pnpm patch-commit` workflow
to produce a committed, reproducible patch file.

**Leaving patches indefinitely** — patches accumulate technical debt. Track each patch with an
upstream issue reference and a target removal version in a comment at the top of the `.patch` file.

**Patching a package range instead of an exact version** — `patchedDependencies` keys must include
an exact version. A patch for `lib@3.2.1` will not be applied to `lib@3.2.2`, even if the bug
persists. Re-run `pnpm patch` after updating the dependency version.

## Gotchas

- pnpm 8 changed the temporary directory location from a system temp path to a path inside the
  project's `.pnpm-patches/` staging area on some platforms. Use the path printed by `pnpm patch`
  — do not hardcode `/tmp/`.
- If the patch was created against version `3.2.1` and the lockfile resolves to `3.2.2` (e.g.,
  from a `^3.2.0` range), pnpm will **not** apply the patch and will print a warning. Pin to the
  exact version in your `package.json` dependency entry when using patches.
- Type declaration patches (`.d.ts` files) work the same as JS patches but be aware that
  TypeScript may still find the original declarations through the package registry cache in some
  setups. Run `tsc --noEmit` after patching to verify types resolve correctly.
- `pnpm audit` results are based on the unpatched package version. If your patch addresses a
  CVE, the audit will still report the vulnerability. Document the patch as the mitigation.

## Verification

```bash
# Confirm patch file exists
ls patches/

# Reinstall and check patch application output
pnpm install 2>&1 | grep "patch applied"

# Run tests against the patched package
pnpm test

# Compare original vs patched
diff <(pnpm --package=some-library@3.2.1 dlx cat dist/index.js) \
     node_modules/some-library/dist/index.js
```

## Related

- `pnpm-workspace-setup.md` — pnpm workspace basics
- `pnpm-overrides-materialization.md` — forcing dependency version ranges
- `renovate-dependency-update-automation.md` — automated dependency updates (remove patches promptly)
- `dependency-audit-pnpm-overrides.md` — audit and override workflow

## Sources

- pnpm documentation: "Patching packages" — pnpm.io/cli/patch
- pnpm changelog: `patch` command added in v7.4 (2022)
- pnpm GitHub issues — versioned patch key behaviour discussion
- `patch-package` README — historical context for the pattern
