# sbom-licenses-2026

**Issue:** A team ships software with 200 npm dependencies. A CVE drops in a transitive dependency. The team doesn't know which package is affected. The team also doesn't know if the license is compatible. The team has no SBOM.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

An SBOM (Software Bill of Materials) lists every component in a software artifact. A license file lists every license. The 2026 default for compliance and security is both: SPDX or CycloneDX for the SBOM, and a clear license policy for distribution.

## Root cause

SBOMs are mandated by US Executive Order 14028 (May 2021), EU NIS2 (effective 2024), EU Cyber Resilience Act (effective 2027), and many sectoral regulations. The 2026 production pattern: CycloneDX or SPDX SBOMs + license policy + automated generation in CI.

## The 4 SBOM standards

| Standard | Maintainer | Focus | Use case |
|---|---|---|---|
| SPDX | Linux Foundation | license focus | legal compliance |
| CycloneDX | OWASP | security + license | vulnerability tracking |
| SWID | NIST | software identification | US federal |
| in-toto | in-toto project | supply chain integrity | verifiable builds |

The 2026 default: CycloneDX for security focus; SPDX for legal focus. Many tools emit both.

## The 5 SBOM fields (CycloneDX)

| Field | Description | Example |
|---|---|---|
| `bomFormat` | standard | `CycloneDX` |
| `specVersion` | version | `1.6` |
| `version` | SBOM version | `1` |
| `components` | every dep with name, version, license, hash | 200 entries |
| `dependencies` | relationship graph | package A depends on B |

The 5 fields are the CycloneDX minimum; SPDX has different fields.

## The 5 best practices

1. **Generate SBOM in CI.** Every build emits a fresh SBOM.
2. **Store SBOMs as build artifacts.** They live alongside the binary.
3. **Distribute SBOM to consumers.** US federal requires SBOMs for software procurement.
4. **Track SBOM changes over time.** New dep = new SBOM; track the diff.
5. **Combine with vulnerability scanning.** SBOM + vulnerability DB = affected packages.

The 5 practices are 2026 production baseline.

## The 5 SBOM tools

| Tool | Strength | License |
|---|---|---|
| Syft (Anchore) | multi-ecosystem, fast | Apache 2.0 |
| Trivy (Aqua) | security + SBOM | Apache 2.0 |
| cdxgen (CycloneDX) | CycloneDX-native | Apache 2.0 |
| SPDX SBOM Generator | SPDX-native | Apache 2.0 |
| Snyk | security focus | commercial |

The 2026 default: Syft for multi-ecosystem, cdxgen for CycloneDX-specific. Trivy for security + SBOM.

## The 5 step SBOM generation in CI

```yaml
# .github/workflows/release.yml
- name: Generate SBOM
  uses: anchore/sbom-action@v0
  with:
    format: cyclonedx-json
    artifact-name: myapp.sbom.cdx.json

- name: Upload SBOM artifact
  uses: actions/upload-artifact@v4
  with:
    name: sbom
    path: myapp.sbom.cdx.json
```

The 5 step workflow: install, generate, format, upload, attach to release.

## The 5 license compliance patterns

| Pattern | When | Tool |
|---|---|---|
| Allow-list | curated set of licenses | FOSSA, Snyk, ScanCode |
| Deny-list | explicit bans (GPL, AGPL for closed source) | FOSSA, Snyk |
| Per-file license headers | legal tradition | manual / lint |
| NOTICE file | required by Apache 2.0 and similar | manual / generated |
| Third-party license aggregation | most open source requires | Gradle, npm, cargo |

The 5 patterns cover the 2026 compliance use cases.

## The 5 license compatibility pairs

| License pair | Compatible? | Notes |
|---|---|---|
| MIT → Apache 2.0 | yes | MIT permits sublicensing |
| Apache 2.0 → MIT | no (license change required) | Apache 2.0 is more restrictive |
| BSD-3 → proprietary | yes | BSD permits proprietary |
| GPL → Apache 2.0 | no | GPL is copyleft |
| Apache 2.0 → GPL | yes | GPL allows Apache code |

The 5 pairs are the most-asked 2026 license questions.

## The 4 step license policy pattern

1. **Define the policy** — allow-list, deny-list, or per-component
2. **Implement in CI** — license-check tool fails the build on violation
3. **Document exceptions** — some dependencies may require specific licenses
4. **Audit quarterly** — new deps may change the picture

The 4 step policy is the 2026 production baseline.

## The 5 step CI integration

```yaml
# .github/workflows/license-check.yml
name: License check
on: [pull_request]

jobs:
  license-check:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run ScanCode
        run: |
          pip install scancode-toolkit
          scancode --license --only-findings . > license-findings.json
      - name: Check for denied licenses
        run: |
          # Fail if GPL, AGPL, or other denied licenses
          if grep -E "GPL|AGPL" license-findings.json; then
            echo "Denied license found"
            exit 1
          fi
```

The 5 step CI integration catches license issues at PR time.

## The 4 step SBOM + vulnerability scanning

Combine SBOM with vulnerability DB for affected packages.

1. **Generate SBOM** — Syft, cdxgen
2. **Scan SBOM against vulnerability DB** — Grype, Trivy, OSV
3. **Identify affected packages** — by name, version, CVE
4. **Trigger alerts** — Slack, email, ticket

The 4 step pattern is the 2026 supply chain security baseline.

## The 5 license types you should know

| License | Use | Restrictions |
|---|---|---|
| MIT | permissive, no restrictions | include copyright notice |
| Apache 2.0 | permissive, with patent grant | include NOTICE file |
| BSD-3-Clause | permissive, no endorsement clause | include copyright notice |
| GPL-3.0 | copyleft, derivative works must be GPL | strong copyleft |
| AGPL-3.0 | network copyleft, SaaS must be open | strong network copyleft |

The 5 license types are the 2026 must-know; AGPL is the controversial one for SaaS.

## The 4 step FOSS license compliance

For FOSS distribution:

1. **Inventory all components** — SBOM
2. **Check license compatibility** — FOSSA, Snyk, or manual review
3. **Generate NOTICE file** — aggregated third-party licenses
4. **Distribute the NOTICE** — alongside the binary or in the repo

The 4 step FOSS pattern is the 2026 production baseline.

## The 5 best practices for SBOMs in 2026

1. **Use CycloneDX or SPDX, not both** for distribution; one is enough.
2. **Generate in CI, not manually.** Manual SBOMs are stale.
3. **Track version-to-version changes.** SBOM diff over time shows what changed.
4. **Combine with license policy.** SBOM lists components; license policy tells you what's allowed.
5. **Sign the SBOM.** Cosign / sigstore signing for the SBOM file too.

## Verification

The tell that SBOM + license compliance is real:

- SBOM is generated in CI for every release
- License policy is in CI; violations fail the build
- SBOM is uploaded as release artifact
- Vulnerability scan runs against SBOM
- NOTICE file is included in distributions

The tell it isn't:

- "We have a wiki page that lists our deps"
- SBOM is generated manually, out of date
- License check is annual, not per-build
- Vulnerability scan is separate from SBOM
- AGPL is in the dep tree and the team didn't notice

## Gotchas

- **SBOM without license info is half the value.** Always include license per component.
- **CycloneDX is JSON; SPDX is multi-format (JSON, YAML, tag:value).** Pick one for tooling.
- **Vulnerability DBs lag reality.** A clean SBOM scan doesn't mean no vulnerabilities.
- **License compatibility is transitive.** A dependency's license affects your project's license.
- **AGPL for SaaS is a deal-breaker.** Don't accidentally pull an AGPL dep into a SaaS product.

## Related

- `worktree/sbom-slsa-2026.md` — SBOM + SLSA + cosign
- `worktree/branch-protection-codeowners-2026.md` — protected branches
- `security/` — security patterns
- `compliance/` — compliance patterns

## Source URLs (verified 2026-08-10)

- https://cyclonedx.org/ — CycloneDX spec
- https://spdx.dev/ — SPDX spec
- https://github.com/CycloneDX/specification — CycloneDX spec repo
- https://github.com/anchore/syft — Syft
- https://github.com/aquasecurity/trivy — Trivy
- https://github.com/CycloneDX/cdxgen — cdxgen
- https://github.com/opensbom-generator/spdx-sbom-generator — SPDX SBOM generator
- https://www.linuxfoundation.org/blog/blog/the-sbom-omnivore — Linux Foundation SBOM analysis
- https://www.ntia.gov/sbom — NTIA SBOM resources
- https://github.com/snyk/snyk — Snyk
