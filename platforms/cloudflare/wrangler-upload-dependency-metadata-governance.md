# Wrangler upload dependency metadata governance

**Issue:** Wrangler now sends declared and exact npm dependency versions with `wrangler deploy` and `wrangler versions upload`. This can improve future supply-chain analysis, but it is deployment metadata, not an SBOM or vulnerability verdict.
**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Controls

- Decide explicitly whether `dependencies_instrumentation.enabled` is on; document any opt-out owner and review date.
- Preserve the lockfile and independent SBOM/provenance controls.
- Verify metadata corresponds to the artifact actually uploaded and review whether package names disclose sensitive internal architecture.

## Verification

1. Upload a staging version and inspect deployment evidence for dependency collection.
2. Change one locked dependency and confirm the metadata changes.
3. Confirm disabling instrumentation does not disable existing dependency scanning or SBOM generation.

## Gotchas

The metadata includes package name, declared range, and exact installed version. Opting out may reduce future analytics; opting in must not be represented as active vulnerability protection.

## Official sources

- https://developers.cloudflare.com/changelog/post/2026-07-07-wrangler-deploy-upload-dependencies-metadata/
- https://developers.cloudflare.com/workers/wrangler/configuration/
