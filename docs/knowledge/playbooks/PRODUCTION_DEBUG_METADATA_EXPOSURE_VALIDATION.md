# Production Debug and Source-Metadata Exposure Validation

## Trigger
Run before production release, after deployment-pipeline changes, after framework/runtime upgrades, and during periodic production-hardening review.

## Inputs
- Exact production artifact/image/package.
- Production runtime configuration.
- Component list including application, framework, runtime, proxy, and server layers.
- Representative production error paths.
- Deployment/configuration-drift monitoring.

## Procedure
1. Inspect the exact production artifact/image/package for `.git`, `.svn`, and other source-control metadata.
2. If source-control metadata is present, verify it is inaccessible both from external request paths and from the running application process; otherwise remove it from the release artifact.
3. Enumerate debug/development mode settings across application, framework, runtime, web/app server, reverse proxy, and other production components.
4. Verify debug/development modes, interactive exception pages, development consoles, hot reload, and development-only servers/endpoints are disabled.
5. Trigger representative exceptions, validation failures, and dependency failures and inspect externally visible responses for debug-only output.
6. Check documented development/diagnostic endpoints and confirm they are absent, disabled, or intentionally protected according to the production design.
7. Verify runtime state directly on the deployed system rather than relying only on build-time configuration or source defaults.
8. Test the deployment/configuration-monitoring path for detection of a controlled change that would re-enable a debug/development setting in a safe environment.
9. Record any copied workspace, image-layer, or packaging behavior that can reintroduce development artifacts into production.
10. Remediate and repeat all failed artifact and runtime tests.

## Escalation
Escalate reachable source-control metadata, production debug/development modes, interactive debug output, or deployment paths that can silently reintroduce development artifacts or settings.

## Evidence
- Production artifact/image inspection.
- External and application-process metadata-access tests.
- Component debug-mode inventory.
- Error-path response samples.
- Runtime configuration evidence.
- Drift-detection test.
- Findings and retest evidence.

## Completion criteria
The production artifact and runtime expose no source-control metadata or debug/development functionality beyond intentionally approved and protected production behavior.

## Source basis
- OWASP ASVS 5.0.0 requirements V13.4.1 and V13.4.2: https://github.com/OWASP/ASVS/blob/v5.0.0/5.0/docs_en/OWASP_Application_Security_Verification_Standard_5.0.0_en.csv
