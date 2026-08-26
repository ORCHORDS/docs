# Semantic Release Automation

Date: 2026-08-17
Author: the platform team
Status: published

## Symptom

Version bumps are done manually and inconsistently, CHANGELOG
entries drift from what actually shipped, or npm publishes happen
from developer laptops with no audit trail.

## Context

`semantic-release` reads conventional commit messages since the
last Git tag, determines the next semver (patch / minor / major),
writes a CHANGELOG, publishes the package, and creates a GitHub
Release — all from CI. The commit type drives the bump:
`fix:` → patch, `feat:` → minor, `BREAKING CHANGE:` → major.

## Conventional Commit Parsing

| Commit prefix      | Bump    |
|--------------------|---------|
| `fix:`             | patch   |
| `feat:`            | minor   |
| `BREAKING CHANGE:` | major   |
| `chore:`, `docs:`  | no bump |

```js
// release.config.js
export default {
  branches: ["main", { name: "next", prerelease: true }],
  plugins: [
    ["@semantic-release/commit-analyzer", {
      preset: "conventionalcommits",
      releaseRules: [
        { type: "refactor", release: "patch" },
        { type: "perf",     release: "patch" },
      ],
    }],
    "@semantic-release/release-notes-generator",
    "@semantic-release/changelog",
    "@semantic-release/npm",
    "@semantic-release/github",
    ["@semantic-release/git", {
      assets: ["CHANGELOG.md", "package.json"],
      message:
        "chore(release): ${nextRelease.version} [skip ci]",
    }],
  ],
};
```

## Release Branches Config

```js
branches: [
  "main",                              // stable releases
  "maintenance/1.x",                   // old line: 1.x.x
  { name: "beta",  prerelease: true }, // 2.0.0-beta.1
  { name: "alpha", prerelease: true }, // 2.0.0-alpha.1
]
```

Pushes to `beta` publish `x.y.z-beta.N`; merging to `main`
drops the pre-release suffix and publishes the stable version.

## npm Publish and GitHub Release

`@semantic-release/npm` reads `NPM_TOKEN` from the environment.
Set `"private": true` in `package.json` to skip npm publish
while still getting the GitHub Release and CHANGELOG.

`@semantic-release/github` creates a Release, uploads assets,
and comments on merged PRs:

```js
["@semantic-release/github", {
  assets: [{ path: "release/*.tgz", label: "Package tarball" }],
  successComment:
    "Included in version ${nextRelease.version}.",
  releasedLabels: ["released"],
}]
```

## Monorepo with @semantic-release/exec

```jsonc
// packages/api/release.config.js
{
  "tagFormat": "api-v${version}",
  "plugins": [
    "@semantic-release/commit-analyzer",
    "@semantic-release/release-notes-generator",
    ["@semantic-release/npm", { "pkgRoot": "packages/api" }],
    ["@semantic-release/exec", {
      "prepareCmd": "pnpm --filter api run build"
    }],
    "@semantic-release/github"
  ]
}
```

Run each package: `cd packages/api && npx semantic-release`.

## CI Setup in GitHub Actions

```yaml
# .github/workflows/release.yml
on:
  push:
    branches: [main, beta, "maintenance/*"]

permissions:
  contents: write
  issues:   write
  pull-requests: write
  id-token: write   # npm provenance

jobs:
  release:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0          # full history for tags
          persist-credentials: false
      - uses: actions/setup-node@v4
        with: { node-version: 22, cache: pnpm }
      - run: pnpm install --frozen-lockfile
      - run: pnpm run build
      - name: Release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          NPM_TOKEN:    ${{ secrets.NPM_TOKEN }}
        run: npx semantic-release
```

## Anti-patterns

- Running `semantic-release` locally — it tags, publishes, and
  creates a GitHub Release from your machine.
- Squash-merging without preserving the `feat:` prefix in the
  merge commit; semantic-release sees only `chore:` and skips.
- Omitting `[skip ci]` in the release commit message, causing
  the workflow to trigger itself recursively.

## Gotchas

- `fetch-depth: 0` is mandatory — semantic-release walks tag
  history to find what changed since the last release.
- `GITHUB_TOKEN` needs `contents: write`; the default read-only
  token fails silently on tag push.
- npm provenance requires a public registry; scoped private
  packages are unsupported.

## Verification

```bash
# Dry run — prints release plan, no side effects
npx semantic-release --dry-run --no-ci

# Debug commit analysis
npx semantic-release --dry-run --no-ci --debug 2>&1 | \
  grep -E "(commits|release|version)"
```

## Related

- /documentation/docs/policies/worktree/conventional-commits-2026.md
- /documentation/docs/policies/worktree/release-please-semantic-release.md
- /documentation/docs/policies/worktree/monorepo-versioning-independent-releases.md
- /documentation/docs/policies/worktree/release-branch-strategy-gitflow-trunk.md
- /documentation/docs/policies/worktree/ci-cd-pipeline-2026.md

## Source URLs (verified 2026-08-17)

- https://semantic-release.gitbook.io/semantic-release/
- https://github.com/semantic-release/semantic-release
- https://github.com/semantic-release/commit-analyzer
- https://github.com/semantic-release/github
- https://docs.npmjs.com/generating-provenance-statements
