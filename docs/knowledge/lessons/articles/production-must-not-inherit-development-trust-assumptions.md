# Production Must Not Inherit Development Trust Assumptions

**Issue:** A production deployment is built or copied from a development workspace, so source-control metadata, interactive debug behavior, or development-only runtime features accidentally remain available after release.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP ASVS 5.0.0 V13.4.1 requires source-control metadata such as `.git` or `.svn` to be absent or inaccessible both externally and to the application, while V13.4.2 requires debug modes to be disabled for all production components. Production safety has to be verified at the deployed runtime and artifact level, not inferred from developer intention.

## Engineering rule

- Build production artifacts from an explicit release process rather than copying an unrestricted development workspace.
- Exclude source-control metadata and verify the running application cannot reach it even when it is not web-served.
- Disable framework, runtime, proxy, server, and application debug/development modes in production.
- Test deployed error paths and diagnostic endpoints for development-only behavior.
- Detect configuration drift that can re-enable debug or development features after deployment.

## Verification

- Inspect the deployed artifact/image/package for source-control metadata and development-only files.
- Attempt external and application-process access to source-control metadata and confirm denial/absence.
- Trigger a representative production exception and confirm no interactive debug page, console, or development diagnostic response is exposed.

## Official source

- OWASP ASVS 5.0.0 requirements V13.4.1 and V13.4.2: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
