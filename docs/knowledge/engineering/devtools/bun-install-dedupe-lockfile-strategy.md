# Bun Install Dedupe Lockfile Strategy

Bun is a JavaScript runtime and package manager whose install path is
built around a single lockfile (`bun.lock`, with the newer text format
replacing `bun.lockb` by default) and a global content-addressable
cache. The recurring engineering question is how to keep the dependency
graph deduplicated: multiple versions of the same library inflate
installs, slow cold CI caches, and — worse — split types and runtime
behavior when two copies of a utility coexist. Bun approaches this
differently from npm: it hoists to a flat `node_modules` by default,
supports npm-style `dedupe` and `overrides`, and its lockfile is
designed to be committed, diffed, and audited. A deliberate dedupe
strategy makes the lockfile a governance artifact instead of noise.

## Scope

Managing dependency duplication and the lockfile in projects using Bun
as the package manager: install and update semantics, deduplication
commands, overrides for forcing versions, monorepo workspaces, and CI
practices around the lockfile. Not covered: Bun's runtime APIs or
bundling.

## Workflow or implementation guidance

1. **Commit the lockfile and read it in review.** Bun's lockfile is a
   text document resolving every workspace and dependency to an exact
   version and integrity hash. A dependency pull request without the
   lockfile diff is unreviewable; the diff is where "why did we gain
   three copies of `ms`" gets answered before merge.
2. **Understand what install does with ranges.** `bun install` resolves
   semver ranges against the registry, preferring versions that
   satisfy the fewest distinct new entries, and reuses the global cache
   so repeated installs are local operations. In workspaces, hoisting
   keeps a single copy at the root where versions are compatible —
   duplication appears only when requirements genuinely conflict.
3. **Run the dedupe command as a hygiene pass.** After long-lived
   branches merge, accumulated duplicate versions can collapse when a
   newer shared version satisfies every range. Bun provides the
   npm-familiar spelling:

   ```bash
   bun install --dedupe   # re-resolve ranges, collapsing redundant duplicates
   bun dedupe             # equivalent shorthand in recent versions
   ```

   Review the resulting lockfile diff: dedupe should only remove
   duplicate resolution entries, never introduce unexpected new
   packages.
4. **Use overrides when a duplicate must be forced away.** When one
   transitive path pins an old, duplicated, or vulnerable version,
   Bun's `overrides` in `package.json` forces the resolution for the
   whole tree:

   ```json
   {
     "overrides": {
       "lodash": "4.17.21",
       "node-fetch": "^3.3.2"
     }
   }
   ```

   Apply overrides surgically — an override is a standing decision that
   silences the resolver, so record why it exists and revisit it each
   quarter.
5. **Drive upgrades deliberately with update.** `bun update` moves
   in-range versions forward and refreshes the lockfile;
   `bun update <pkg>` scopes it. For dedupe purposes the useful
   sequence is update the direct dependencies first (which often
   widens compatible shared versions), then run the dedupe pass, then
   verify the app — not the reverse, where dedupe fights against stale
   top-level ranges.
6. **Treat workspaces as the structural fix.** In monorepos, duplicate
   copies frequently come from apps depending on slightly different
   ranges of shared libraries. Prefer a single version source — a
   catalog-style shared constants package, or consistent ranges across
   apps — so the resolver never has conflicting requirements to
   satisfy with two copies.
7. **Wire the lockfile into CI.** Install with `bun install
   --frozen-lockfile` (or `--ci`) on CI so an uncommitted or edited
   lockfile fails the build rather than silently resolving fresh
   versions. Cache the global Bun cache directory keyed on the lockfile
   hash; cold installs then become link operations from cache.

## Controls

- **Frozen installs in CI.** CI must never rewrite the lockfile; the
  flag that fails on drift is the control that makes the committed file
  authoritative.
- **Duplicate budget.** Spot-check with a tool that walks
  `node_modules` (or parse the lockfile) for packages resolved to more
  than two versions. Zero duplicates is not the goal — a bounded,
  explainable count is.
- **Override ledger.** Keep a short comment block or table mapping each
  override to the reason and the removal condition, ideally with the
  issue that forced it.
- **Cache integrity.** Bun verifies integrity hashes from the lockfile
  when installing from cache; never hand-edit the lockfile to work
  around a registry problem — regenerate it with the tool.

## Validation evidence

1. After any dedupe or update pass, run the application's test suite
   and typecheck; a dedupe that changed behavior means two copies were
   load-bearing and the merge needs a compatibility decision, not a
   mechanical collapse.
2. Count duplicate resolutions before and after: compare the number of
   distinct versions per package in the lockfile (the diff itself shows
   removed duplicate entries), and confirm the count only decreased.
3. Prove frozen mode works: edit a dependency version in `package.json`
   without regenerating, run the CI install command locally, and
   confirm it fails with a lockfile-mismatch error rather than
   resolving.
4. Prove cache determinism: run `bun install` twice from a clean
   `node_modules` and confirm the lockfile is unchanged (no version
   churn between runs).
5. For each override, install and confirm the forced version is what
   actually lands in `node_modules` for every consumer path, using the
   runtime import of the package as the check.

## Failure modes and correction

- **Duplicate count never drops.** Conflicting top-level ranges are
  pinning the split; align the ranges or accept the duplicate
  deliberately, then record it. Dedupe cannot fix a contradiction.
- **Dedupe introduces breakage.** A shared instance assumed its own
  private module state (singletons, `instanceof` checks, duplicate
  React copies break hooks). Roll back the collapse for that package,
  and fix the root cause (peer dependencies declared correctly) before
  retrying.
- **Lockfile churn on every install.** Usually caused by
  platform-specific optional dependencies or a registry proxy serving
  moving metadata; pin the registry, ensure the same Bun version runs
  locally and in CI, and regenerate once to stabilize.
- **`bun.lockb` versus `bun.lock` confusion.** The binary format is
  legacy; mixed state (both files present) resolves unpredictably.
  Delete the stale one, regenerate, and commit only the current
  format's file.
- **Override stops being needed.** The upstream package fixed the
  range, but the override keeps forcing an old version silently.
  Audit overrides on a schedule by removing one at a time and running
  the frozen install plus tests.

## Limitations

- Bun's override mechanics and flag spellings have evolved between
  releases; verify against the version pinned in the repository before
  scripting around them.
- Hoisting behavior differs from pnpm's strict isolated layout, so
  phantom-dependency problems (importing packages you never declared)
  can hide until the layout changes.
- The lockfile reflects npm-registry metadata; patched or vendored
  packages outside the registry are outside this strategy.

## Canonical sources

- Bun documentation, `bun install` (including dedupe and
  frozen-lockfile behavior): https://bun.sh/docs/cli/install
- Bun documentation, `bun update`: https://bun.sh/docs/cli/update
- Bun documentation, Lockfile: https://bun.sh/docs/install/lockfile
- Bun GitHub repository: https://github.com/oven-sh/bun
