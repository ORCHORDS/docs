# Deploy-artifact build parity in CI

**Date:** 2026-08-19
**Status:** verified-live
**Category:** deploy

## Symptom

A pull request passes the application's ordinary framework build, typecheck, and unit tests, but the release pipeline later fails while compiling a platform-specific server artifact.

The failure can look surprising because the source is valid TypeScript/JavaScript and the static or framework output already exists. The missing proof is that the *deployment artifact* has its own compiler, bundler, routing transform, or runtime constraints that ordinary application CI never exercised.

## Root cause

CI validated a convenient developer build rather than the same artifact-producing boundary used by deployment.

For Cloudflare Pages Functions, the `/functions` directory is server-side code that Pages turns into a Worker with file-based routes. Wrangler exposes a dedicated `pages functions build` command whose purpose is to compile a Pages Functions directory into a Worker bundle. Passing a framework build alone therefore does not prove that imports, routing, compatibility constraints, or server-side bundling for Pages Functions are valid.

This pattern is broader than one platform: whenever deployment invokes an additional compiler, packager, manifest generator, container build, native toolchain, serverless bundler, or policy transform, that transformation is part of the release contract and needs pre-merge evidence.

## Patterns

### Validate the artifact-producing command before merge

Run the same non-deploying compiler/bundler that release uses, with the same pinned tool version and relevant configuration.

For a Pages Functions project, a secretless contract lane can run a command such as:

```sh
wrangler pages functions build ./functions --outdir ./.wrangler-ci
```

Then assert that the expected output Worker exists and is non-empty.

The gate should compile only; it should not require production credentials or create a deployment.

### Keep framework and platform builds distinct

Name checks according to what they prove. For example:

- `web-build` — framework/static application build;
- `pages-functions-build` — server-side Pages Functions bundle;
- `container-build` — OCI image construction;
- `migration-plan` — migration artifact/plan generation.

Do not let one green check imply coverage of another build boundary.

### Pin the deployment toolchain

Use the repository-reviewed Wrangler/package-manager/toolchain version rather than downloading an unreviewed latest executable during the validation job.

### Scope the trigger to relevant inputs

A platform-artifact build can use path filters for its function source, shared modules that it imports, platform configuration, lockfiles, and the workflow itself. Ensure branch-protection policy does not require a context that disappears on unrelated changes; use an applicability/aggregate pattern when necessary.

### Fail closed on build absence

The validation must fail when:

- the platform compiler exits non-zero;
- the expected artifact is absent or empty;
- a required shared import cannot be bundled;
- generated routing/configuration is invalid;
- the job was expected to run but was unexpectedly skipped.

## Anti-patterns

- Treating `npm run build` or a framework build as proof that every deployable server artifact is valid.
- Discovering a Pages Functions bundling error for the first time inside the production deployment job.
- Adding production credentials to a compile-only PR job when the compiler does not need them.
- Reimplementing the platform bundler with a generic TypeScript check instead of exercising the real artifact boundary.
- Marking a deployment-specific build as optional because application tests already passed.
- Compiling against a different tool version or configuration than the release pipeline.

## Checklist

- [ ] Identify every compiler/bundler/package step executed after the ordinary application build.
- [ ] Determine which of those can run without deployment credentials.
- [ ] Add a pre-merge check for each independently failure-prone deploy artifact.
- [ ] Use the repository-pinned platform CLI/tool version.
- [ ] Reuse the same source directory and material configuration as release.
- [ ] Assert the output artifact exists and is non-empty/parseable as appropriate.
- [ ] Include shared-module and platform-config changes in the trigger scope.
- [ ] Keep deployment itself separate from the compile-only gate.
- [ ] Record the exact SHA validated by the artifact build.
- [ ] Re-run after rebases or changes to the deployment baseline.

## Verification

A useful proof sequence is:

1. Start from a clean checkout of the exact pull-request SHA.
2. Install dependencies from the reviewed lockfile.
3. Run the ordinary framework build and its normal checks.
4. Run the actual platform artifact compiler/bundler used by release.
5. Assert its output exists and is non-empty.
6. Introduce an intentionally unbundleable server-side import in a test branch/fixture and confirm the platform-artifact check fails even if the framework build remains green.
7. Remove the fixture, rerun, and retain the successful exact-SHA result.

## Gotchas

- A framework may exclude a platform's `functions/` directory from its own compilation, so green framework TypeScript/build evidence can be completely orthogonal to the deploy artifact.
- Cross-package imports may typecheck but still fail a platform bundler because of module format, runtime API, compatibility, or resolution rules.
- File-based serverless routing is often generated during the platform build; route validity therefore belongs to that build boundary.
- A deployment command may combine compilation and mutation. Prefer the platform's compile/build subcommand for pull requests so validation remains secretless and non-mutating.
- If deployment configuration is the source of truth, ensure CI consumes the same reviewed configuration rather than a parallel hand-written test configuration.

## Related

- CI contract drift and structural selectors
- Reproducible builds and lockfile-pinned tooling
- Exact-SHA deployment gates
- Secretless pull-request validation
- Fail-closed release evidence

## Sources

- Cloudflare Pages Functions overview: https://developers.cloudflare.com/pages/functions/
- Wrangler Pages commands — `pages functions build`: https://developers.cloudflare.com/workers/wrangler/commands/pages/
- Cloudflare Pages Functions routing: https://developers.cloudflare.com/pages/functions/routing/
- Cloudflare Pages local development: https://developers.cloudflare.com/pages/functions/local-development/
