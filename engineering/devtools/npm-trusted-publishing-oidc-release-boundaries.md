# npm trusted publishing and OIDC release boundaries

**Issue:** Package publishing depends on a long-lived npm token in CI, increasing credential exposure and making publisher identity harder to constrain.
**Date:** 2026-08-17
**Author:** ORCHORDS
**Status:** documented

## Decision

Where supported, use npm trusted publishing with OIDC for release workflows instead of a reusable publishing token. Bind the trusted publisher to the exact repository, workflow file, and environment appropriate to the package.

## Operating model

During a supported CI run, npm validates the workload identity supplied through OIDC and issues short-lived credentials for the publish operation. The trust configuration is package-specific and should describe only the release workflow, not general CI.

## Implementation checklist

1. Create a dedicated release workflow and protect the release environment.
2. Configure npm trusted publishing for the precise GitHub repository, workflow filename, and, when used, environment.
3. Grant the workflow only the OIDC permissions it needs; avoid passing registry credentials to unrelated jobs.
4. Pin external actions, publish from a clean, reproducible build, and verify the package/version after publish.
5. Keep a documented, separately controlled break-glass process; do not leave a fallback token in normal CI variables.
6. Audit package access and trusted-publisher configuration whenever ownership or release workflows change.

## Guardrails

- Trusted publishing reduces long-lived-token exposure; it does not make a compromised release workflow safe.
- Do not allow pull-request workflows to run the publishing path.
- Treat package provenance, release tags, and registry publication verification as separate controls.

## Sources

- [npm: trusted publishing](https://docs.npmjs.com/trusted-publishers/)
