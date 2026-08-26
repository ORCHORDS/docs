# Changesets Pre-release Channel Management

Date: 2026-08-23 / Author: example.com / Status: production

---

## Symptom / Use-case

The team needs to ship a breaking API change to `@example project/sdk` for early adopters
to test before it becomes the stable release. Publishing a regular semver bump
would mark the package as latest on npm, forcing all consumers to upgrade.
Instead, you need a `next` or `beta` channel where versions are tagged
`@next` on npm and existing `@latest` consumers are unaffected.

---

## Context

Changesets' pre-release mode (introduced in `@changesets/cli` ≥ 2.14) solves
this via a persistent `.changeset/pre.json` state file. When in pre-release
mode:

- Version bumps produce `1.5.0-next.0`, `1.5.0-next.1`, etc.
- `pnpm changeset publish` tags the release as `next` (not `latest`) on npm.
- The pre.json file is committed to the branch so CI knows to continue the
  pre-release sequence.

On exiting pre-release mode, Changesets collapses all the pre-release bumps
into a single stable version bump and publishes it as `latest`.

Pre-release channels available: `next`, `beta`, `alpha`, `rc`, or any custom
string. The channel name becomes both the npm dist-tag and the semver
pre-release identifier.

---

## Entering pre-release mode

```bash
# On the feature branch (e.g. feat/v2-api)
pnpm changeset pre enter next
```

This creates `.changeset/pre.json`:

```json
{
  "mode": "pre",
  "tag": "next",
  "initialVersions": {
    "@example project/sdk": "1.4.2",
    "@example project/core": "0.9.1"
  },
  "changesets": []
}
```

Commit this file immediately:

```bash
git add .changeset/pre.json
git commit -m "chore: enter changesets pre-release mode (next)"
```

---

## Adding changesets during pre-release

The workflow is identical to normal changeset authoring:

```bash
pnpm changeset add
# Prompts: which packages? major/minor/patch? summary?
```

Changesets written during pre-release are tracked in `pre.json`:

```json
{
  "changesets": [
    "brave-cats-dance",
    "angry-dogs-sleep"
  ]
}
```

---

## Versioning during pre-release

```bash
pnpm changeset version
```

For the first run, packages are bumped to `1.5.0-next.0`:

```
@example project/sdk: 1.4.2 → 1.5.0-next.0
@example project/core: 0.9.1 → 1.0.0-next.0
```

Subsequent runs (after adding more changesets) increment the pre-release
counter:

```
@example project/sdk: 1.5.0-next.0 → 1.5.0-next.1
```

The counter restarts at 0 only when a new changeset with a _higher_ semver
bump is added.

---

## Publishing to the next channel

```bash
pnpm changeset publish --tag next
```

npm receives the publish with `--tag next`. Consumers can install:

```bash
npm install @example project/sdk@next
# or
pnpm add @example project/sdk@next
```

The `@latest` dist-tag is NOT moved; existing consumers are unaffected.

Verify the dist-tag on npm:

```bash
npm dist-tag ls @example project/sdk
# @example project/sdk:
#   latest: 1.4.2
#   next: 1.5.0-next.2
```

---

## CI automation for the next channel

```yaml
# .github/workflows/pre-release.yml
name: Pre-release publish

on:
  push:
    branches: ['feat/v2-*', 'next']

jobs:
  publish-next:
    runs-on: ubuntu-latest
    # Only run if pre.json exists (i.e., pre-release mode is active)
    if: ${{ hashFiles('.changeset/pre.json') != '' }}
    permissions:
      contents: write          # to commit version bumps
      id-token: write          # for npm provenance
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: pnpm/action-setup@v4
        with:
          version: 9

      - uses: actions/setup-node@v4
        with:
          node-version: 20
          registry-url: https://registry.npmjs.org

      - run: pnpm install --frozen-lockfile

      - name: Build packages
        run: pnpm turbo run build

      - name: Version (pre-release)
        run: pnpm changeset version
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}

      - name: Publish (next tag)
        run: pnpm changeset publish --tag next
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}

      - name: Commit version bump
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
          git add -A
          git diff --staged --quiet || git commit -m "chore: version packages (pre-release)"
          git push
```

---

## Exiting pre-release and publishing stable

When the feature is ready:

```bash
# On the release branch / main
pnpm changeset pre exit
```

This updates `.changeset/pre.json` to `"mode": "exit"` and re-enters the
changeset collection phase. Running `pnpm changeset version` now collapses all
the pre-release bumps into a single stable version:

```
@example project/sdk: 1.5.0-next.3 → 1.5.0
@example project/core: 1.0.0-next.1 → 1.0.0
```

The `pre.json` file is deleted after version is run successfully.

```bash
pnpm changeset version
git add -A
git commit -m "chore: version packages for stable release"

pnpm changeset publish          # no --tag; defaults to latest
```

After publishing, move the `next` dist-tag back to the new latest (optional
cleanup):

```bash
npm dist-tag add @example project/sdk@1.5.0 latest
npm dist-tag rm @example project/sdk next
```

---

## Multiple simultaneous channels (alpha + beta)

Changesets does not support multiple active pre-release modes in the same
branch. Use separate branches per channel:

```
main         → @latest
feat/v2-api  → @next    (.changeset/pre.json: mode=pre, tag=next)
feat/v3-api  → @alpha   (.changeset/pre.json: mode=pre, tag=alpha)
```

Each branch maintains its own `pre.json`. CI workflows gate on the branch name:

```yaml
on:
  push:
    branches:
      - 'feat/**'
```

---

## Pinning consumers to a pre-release channel

Internal Workers apps that want to test the `next` channel should pin with an
exact pre-release version, not the `@next` dist-tag, to avoid unintentional
upgrades in CI:

```jsonc
// packages/my-worker/package.json
{
  "dependencies": {
    "@example project/sdk": "1.5.0-next.2"   // pinned pre-release
  }
}
```

Or use Renovate to automate pre-release tracking:

```json5
// renovate.json
{
  "packageRules": [
    {
      "matchPackagePatterns": ["^@example project/"],
      "ignoreUnstable": false,      // allow pre-release versions
      "matchUpdateTypes": ["major", "minor", "patch", "pin", "digest"]
    }
  ]
}
```

---

## Anti-patterns

- **Merging the pre-release branch into main with `pre.json` still active** —
  main enters pre-release mode and stable publishes stop working. Always
  `pnpm changeset pre exit` before merging.
- **Running `pnpm changeset publish` without `--tag next`** — the pre-release
  version becomes `@latest`, overriding the stable tag for all consumers.
- **Deleting `pre.json` manually** — the Changesets CLI loses track of the
  initial versions and may compute incorrect version bumps on `pre exit`. Use
  `pnpm changeset pre exit` instead.
- **Publishing a pre-release without a build step** — `dist/` contains stale
  artifacts and the published package is broken.
- **Using `pnpm changeset version` on the wrong branch** — version commits land
  on the wrong branch; the pre-release counter resets.

---

## Gotchas

- `pnpm changeset pre enter next` must be run from the **workspace root**,
  not from within a package directory.
- The pre-release identifier (`next`) is appended to the version's
  **pre-release** segment, not the build metadata segment. `1.5.0-next.0` is
  correct; `1.5.0+next.0` is wrong and would still count as stable semver.
- Changesets respects `private: true`. Private packages are versioned (their
  `package.json` is updated) but never published, even in pre-release mode.
- If you run `pnpm changeset version` twice without a new changeset in between,
  the second run is a no-op (the counter is NOT incremented). A new changeset
  must be added to trigger a counter bump.
- The GitHub Actions `actions/checkout` step must use `fetch-depth: 0` so
  Changesets can compare tags and determine which packages have changed.

---

## Verification

```bash
# 1. Confirm pre.json is present and correct
cat .changeset/pre.json | jq '{mode,tag}'

# 2. Dry-run version bump
pnpm changeset version --snapshot test-dry-run
git checkout -- .              # discard dry-run changes

# 3. Confirm npm tag after publish
npm dist-tag ls @example project/sdk

# 4. Confirm @latest is untouched
npm info @example project/sdk dist-tags.latest
```

---

## Related

- `documentation/docs/policies/worktree/changesets-automated-npm-publish-ci-pipeline.md`
- `documentation/docs/policies/worktree/changesets-ci-enforcement-gate-workers.md`
- `documentation/docs/policies/worktree/monorepo-versioning-independent-releases.md`
- `documentation/docs/policies/worktree/release-management-2026.md`
- `documentation/docs/policies/worktree/feature-flags-2026.md`

---

## Sources

- Changesets pre-release documentation — https://github.com/changesets/changesets/blob/main/docs/prereleases.md
- Changesets CLI — `pre` command — https://github.com/changesets/changesets/blob/main/packages/cli/README.md#pre
- npm dist-tag reference — https://docs.npmjs.com/cli/v10/commands/npm-dist-tag
- Semver pre-release spec — https://semver.org/#spec-item-9
