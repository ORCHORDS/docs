# Software Supply Chain Failure Review

## Trigger
Run before major releases, after material dependency/build/distribution changes, after a supply-chain incident or advisory, and during periodic application-security review.

## Inputs
- Dependency inventory/SBOM or equivalent resolved dependency evidence.
- Runtime, server, database, build-tool, package-source, and deployment inventories.
- Vulnerability/advisory monitoring sources.
- Build, signing, packaging, distribution, and update-process evidence.
- Component support/maintenance status.

## Procedure
1. Reconcile declared dependencies with resolved/locked direct and transitive dependencies.
2. Include material non-library software such as runtimes, web/application servers, databases, build tools, package managers, CI tooling, and client-side components in the review scope.
3. Verify versions and support/maintenance status for representative high-risk components.
4. Identify unsupported, obsolete, unmaintained, or unupdateable components and assign a disposition and owner.
5. Confirm vulnerability/advisory monitoring covers the ecosystems and products actually used.
6. Trace dependency sources and package repositories and verify they are governed through approved sources or controls.
7. Trace a released artifact through its build, packaging, signing/integrity, distribution, and update paths and identify points where unauthorized modification could enter.
8. Exercise a representative security dependency/update workflow from detection through test and deployment.
9. Review exceptions for unpinned, unmaintained, unsupported, or externally hosted components and confirm owners and review dates.
10. Record findings, remediate, and repeat the relevant reconciliation or update exercise.

## Escalation
Escalate unknown transitive dependencies, unsupported high-exposure components, ungoverned package/build inputs, integrity gaps in build/distribution/update paths, or security updates that cannot be reliably tested and deployed.

## Evidence
- Direct/transitive dependency reconciliation.
- Component version/support evidence.
- Advisory-monitoring coverage.
- Build/distribution/update trace.
- Security update exercise.
- Exceptions and remediation/retest evidence.

## Completion criteria
Material software dependencies and build/distribution/update paths are inventoried, owned, monitored, supportable, and capable of receiving tested security updates, with unresolved supply-chain risks explicitly tracked.

## Source basis
- OWASP Top 10:2025 A03 — Software Supply Chain Failures: https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/
