# sbom-supply-chain-2026

**Issue:** SBOM + supply chain security
**Date:** 2026-08-09
**Status:** documented

## Symptom
Log4Shell hits. You have no idea which apps are
affected. Auditors ask for SBOM. CRA compliance
coming. You wish you had inventory.

## Root cause
**Without SBOM, you don't know what's in your
software.** Generate it.

**Source:** CISA 2026 minimum elements + core.cz 2026.

## The "SBOM" concept

Software Bill of Materials:
- **Inventory:** Every component
- **Direct + transitive:** All deps
- **Versions + licenses:** Per component
- **Machine-readable:** SPDX / CycloneDX
- **Required by:** US EO 14028, EU CRA 2027

The SBOM is the list.

## The "SBOM formats" pattern

For choice:
| Format | Maintainer | Strength |
|---|---|---|
| SPDX | Linux Foundation | License compliance, ISO |
| CycloneDX | OWASP | Security, VEX support |
| SWID | ISO/IEC | Identification standard |

The format is per need.

## The "SPDX" pattern

For SPDX:
- **ISO/IEC 5962:2021**
- **Strong:** License compliance
- **Supports:** JSON, XML, YAML, RDF
- **Used by:** NTIA, federal US

The SPDX is for compliance.

## The "CycloneDX" pattern

For CycloneDX:
- **OWASP:** Standard
- **Strong:** Security + VEX
- **Supports:** Services, ML model BOM
- **Used by:** DevSecOps

The CycloneDX is for security.

## The "format choice" pattern

For choice:
- **CycloneDX:** Security-first
- **SPDX:** License + regulatory
- **Both:** Convert via tools

The choice is per need.

## The "generation stage" pattern

For when:
- **Source:** Analyze manifests (package.json)
- **Build:** Capture resolved deps
- **Binary/Container:** Scan artifact
- **Build-time:** Most accurate (what shipped)

The stage is per accuracy.

## The "Syft" pattern

For generation:
```bash
# Container
syft packages registry.example.com/app:v2.1.0 \
  -o spdx-json > sbom.spdx.json

# Filesystem
syft packages dir:. -o cyclonedx-json

# From package-lock
syft packages lock.json
```

The Syft is the tool.

## The "Trivy" pattern

For scan + SBOM:
```bash
# SBOM + vulnerabilities in one
trivy image --format spdx-json \
  registry.example.com/app:v2.1.0 > sbom.json
```

The Trivy is scanner + SBOM.

## The "cdxgen" pattern

For multi-language:
- **Languages:** 30+
- **Reachability:** Detects
- **Output:** CycloneDX

The cdxgen is rich.

## The "GitHub native" pattern

For GitHub:
- **Dependency graph:** Auto
- **SBOM export:** API
- **Dependabot:** Updates
- **Good start:** Smaller projects

The native is the start.

## The "CRA compliance" pattern

For EU CRA (2027):
- **Required:** SBOM for all products
- **Scope:** Sold in EU
- **Penalty:** Up to €15M or 2.5% revenue
- **Format:** SPDX or CycloneDX

The CRA is mandatory.

## The "2026 CISA minimum" pattern

For CISA 2026:
- **Author signature**
- **Data format name + version**
- **Generation context**
- **Tool name + version**
- **SBOM version**
- **Component hash + algorithm**
- **Component license**
- **Component dependency relationship**
- **Frequency**

The minimum is 10+.

## The "SBOM + SLSA" pattern

For combined:
- **SBOM:** What (components)
- **SLSA:** How (build integrity)
- **Together:** Full provenance

The combo is comprehensive.

## The "SLSA levels" pattern

For levels:
- **L1:** Documented + provenance
- **L2:** Hosted + signed
- **L3:** Hardened + tamper-resistant
- **L4:** Hermetic + two-party

The levels are ascending.

## The "VEX" pattern

For vuln context:
- **Not Affected:** Not called
- **Affected:** Mitigation
- **Fixed:** In version X
- **Under Investigation:** Looking

The VEX is per vuln.

## The "VEX benefit" pattern

For VEX:
- **Reduces:** Alert fatigue
- **Focus:** Actual threats
- **Format:** CycloneDX
- **Process:** Per CVE

The VEX is the filter.

## The "lock files" pattern

For pinning:
- **package-lock.json:** npm
- **Pipfile.lock:** pip
- **go.sum:** Go
- **Cargo.lock:** Rust
- **Rule:** Commit, no floating ranges

The lock is required.

## The "frozen lockfile" pattern

For CI:
```bash
npm ci  # Fails if lockfile out of date
pip install --require-hashes
cargo build --locked
```

The CI enforces.

## The "private registry" pattern

For deps:
- **Artifactory / Nexus:** Proxy
- **Cache:** Local
- **Scan:** Block bad
- **Audit:** All access

The proxy is the gate.

## The "Dependabot / Renovate" pattern

For auto-update:
- **Dependabot:** GitHub native
- **Renovate:** Multi-platform
- **Auto PR:** Yes
- **Review:** Before merge
- **Major:** Manual

The bot is the source.

## The "OpenSSF Scorecard" pattern

For deps:
- **Scorecard:** Evaluates security
- **Criteria:** 18+ (signed, CI tests, etc.)
- **Use:** Filter deps
- **CI:** Per PR

The scorecard is the filter.

## The "Cosign signing" pattern

For artifacts:
- **Cosign:** Sign container/binary
- **Sigstore:** Transparency log
- **Verify:** At deployment
- **Use:** Block unsigned

The signing is the gate.

## The "SBOM in CI" pattern

For pipeline:
```
build → SBOM gen → vuln scan → SBOM sign → SBOM store → deploy
```

The CI is integrated.

## The "SBOM storage" pattern

For store:
- **Dependency-Track:** OWASP
- **Snyk:** Commercial
- **GitHub Dependency Graph:** Built-in
- **Format:** SPDX or CycloneDX
- **Query:** Per CVE

The storage is queryable.

## The "log4shell response" pattern

For CVE:
- **Step 1:** Pull SBOM
- **Step 2:** Find affected
- **Step 3:** Check version
- **Step 4:** Patch or mitigate
- **Time:** < 1 hour (with SBOM)

The response is fast.

## The "no SBOM" anti-pattern

For no SBOM:
- **Issue:** Blind to CVEs
- **Fix:** Generate per build

The SBOM is required.

## The "manifest only" anti-pattern

For manifest:
- **Issue:** Doesn't reflect shipped
- **Fix:** Build-time SBOM

The SBOM is per build.

## The "no lockfile" anti-pattern

For no lock:
- **Issue:** Drift, surprise updates
- **Fix:** Commit lockfile

The lock is committed.

## The "floating versions" anti-pattern

For floats:
- **Issue:** Unpredictable
- **Fix:** Exact versions

The version is exact.

## The "auto-merge major" anti-pattern

For major:
- **Issue:** Breaking changes ship
- **Fix:** Manual review

The major is reviewed.

## The "no SLSA" anti-pattern

For no SLSA:
- **Issue:** Trust the build
- **Fix:** L2 minimum

The SLSA is signed.

## The "no signing" anti-pattern

For unsigned:
- **Issue:** Tampered
- **Fix:** Cosign

The artifact is signed.

## The "SBOM rollout" pattern

For phases:
- **Months 1-2:** Audit + lockfiles + SBOM
- **Months 3-4:** SBOM for all + storage
- **Months 5-6:** SLSA L2 + private registry
- **Ongoing:** VEX + audits

The rollout is staged.

## The "SBOM checklist" pattern

For checklist:
- [ ] SBOM per build
- [ ] SPDX or CycloneDX
- [ ] Build-time (not manifest)
- [ ] Stored queryably
- [ ] VEX for triaged
- [ ] Lock files committed
- [ ] Dependabot / Renovate
- [ ] Cosign signing
- [ ] SLSA L2+
- [ ] CRA ready (if EU)

The checklist is 10.

## Verification
- **Test:** SBOM generated
- **Test:** Vuln scan runs
- **Test:** Log4shell-like response < 1h
- **Test:** CRA audit passes
- **Audit:** Quarterly

## Gotchas
- **The "no SBOM" anti-pattern.** Required.
- **The "manifest only" anti-pattern.** Build-time.
- **The "no signing" anti-pattern.** Cosign.

## Related
- `security/slsa-supply-chain.md`
- `security/owasp-top-10-2025.md`
- `security/container-security-2026.md`
- `cloudflare/containers-best-practices.md`
- `compliance/eu-ai-act.md`
- Codelit: https://codelit.io/blog/supply-chain-security
- CISA: https://media.defense.gov/2026/Jul/29/2003971159/-1/-1/1/CSI_2026_cisa_sbom_minimum_elements_508c.PDF
- core.cz: https://core.cz/en/blog/2026/sbom-supply-chain-security/
