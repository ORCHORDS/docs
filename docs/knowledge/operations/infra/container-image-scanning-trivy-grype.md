# Container Image Scanning with Trivy and Grype

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A container image that passes `docker build` with no warnings can contain dozens of
known CVEs in the base OS packages or language dependencies it inherits. Without automated
image scanning in CI, vulnerabilities accumulate invisibly and only surface during audits,
pen-tests, or — worse — after an incident.

This article covers integrating Trivy and Grype into a CI pipeline to scan images for
OS-level CVEs, language-runtime vulnerabilities, and misconfigurations, and to emit
CycloneDX/SPDX SBOMs as attestable build artifacts. It is distinct from the general
SBOM/SLSA supply-chain article (`supply-chain-security-sbom-slsa.md`), which covers
provenance; this article focuses on vulnerability detection and gating.

## Context

Two dominant open-source image scanners have emerged as production standards:

- **Trivy** (Aqua Security): single binary, scans OS packages (Alpine, Debian, RHEL,
  Ubuntu), language manifests (npm, pip, Go modules, Cargo, Maven, Gradle, Ruby gems),
  IaC files, Kubernetes manifests, and container images in one tool. Supports SARIF,
  CycloneDX, SPDX, and JSON output.
- **Grype** (Anchore): focused exclusively on vulnerability matching against the Anchore
  vulnerability DB, with companion tool Syft for SBOM generation. Grype is excellent when
  you need programmatic vulnerability data; Syft produces richer SBOM trees.

Both tools download vulnerability databases on first run. In CI you must either cache
the DB or point to a pre-populated mirror to avoid rate limits and long cold-start times.

## Trivy — installation and basic use

```bash
# Install (Linux, via apt)
apt-get install -y wget apt-transport-https gnupg lsb-release
wget -qO - https://aquasecurity.github.io/trivy-repo/deb/public.key | gpg --dearmor \
  -o /usr/share/keyrings/trivy.gpg
echo "deb [signed-by=/usr/share/keyrings/trivy.gpg] \
  https://aquasecurity.github.io/trivy-repo/deb $(lsb_release -sc) main" \
  | tee /etc/apt/sources.list.d/trivy.list
apt-get update && apt-get install -y trivy

# Or via binary download
curl -sfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
  | sh -s -- -b /usr/local/bin

# Scan a local image (table output)
trivy image --severity HIGH,CRITICAL my-app:latest

# Scan a local tarball (no daemon needed)
docker save my-app:latest -o my-app.tar
trivy image --input my-app.tar --severity CRITICAL --exit-code 1
```

`--exit-code 1` makes Trivy return a non-zero exit when findings exceed the severity
threshold — the CI step fails automatically.

### Trivy output formats

| Flag                          | Use case                                |
|-------------------------------|-----------------------------------------|
| `--format table`              | Human-readable terminal output          |
| `--format json`               | Machine-readable for downstream tooling |
| `--format sarif`              | GitHub Code Scanning / GHAS upload      |
| `--format cyclonedx`          | SBOM (CycloneDX XML or JSON)            |
| `--format spdx-json`          | SBOM (SPDX JSON)                        |
| `--format template --template @contrib/html.tpl` | HTML report       |

```bash
# Emit CycloneDX SBOM and fail on CRITICAL
trivy image \
  --format cyclonedx \
  --output sbom.cyclonedx.json \
  --severity CRITICAL \
  --exit-code 1 \
  my-app:latest
```

## Grype and Syft

```bash
# Install Grype
curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \
  | sh -s -- -b /usr/local/bin

# Install Syft (SBOM generator)
curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh \
  | sh -s -- -b /usr/local/bin

# Generate SBOM with Syft, then scan SBOM with Grype
syft my-app:latest -o spdx-json > sbom.spdx.json
grype sbom:sbom.spdx.json --fail-on high
```

Scanning an SBOM rather than the live image is faster and can be done offline after the
SBOM is generated — useful for audit trails separate from the build step.

## GitHub Actions integration

```yaml
# .github/workflows/image-scan.yml
name: Image Scan

on:
  push:
    branches: [main]
  pull_request:

jobs:
  scan:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      security-events: write   # required for SARIF upload

    steps:
      - uses: actions/checkout@v4

      - name: Build image
        run: docker build -t my-app:${{ github.sha }} .

      - name: Cache Trivy DB
        uses: actions/cache@v4
        with:
          path: ~/.cache/trivy
          key: trivy-db-${{ github.run_id }}
          restore-keys: trivy-db-

      - name: Run Trivy (SARIF)
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: my-app:${{ github.sha }}
          format: sarif
          output: trivy-results.sarif
          severity: CRITICAL,HIGH
          exit-code: "1"

      - name: Upload SARIF to GitHub Security
        uses: github/codeql-action/upload-sarif@v3
        if: always()    # upload even on scan failure
        with:
          sarif_file: trivy-results.sarif

      - name: Emit CycloneDX SBOM
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: my-app:${{ github.sha }}
          format: cyclonedx
          output: sbom.cyclonedx.json

      - name: Attach SBOM as artifact
        uses: actions/upload-artifact@v4
        with:
          name: sbom-${{ github.sha }}
          path: sbom.cyclonedx.json
          retention-days: 90
```

### Attestation with cosign

To make the SBOM cryptographically tied to the image (SLSA level 2+):

```bash
# Sign the image and attest the SBOM
cosign sign --key cosign.key my-app:${{ github.sha }}
cosign attest \
  --key cosign.key \
  --type cyclonedx \
  --predicate sbom.cyclonedx.json \
  my-app:${{ github.sha }}
```

## Vulnerability database caching

Both Trivy and Grype download their vulnerability DBs on first run. Cold downloads are
~30-60 MB and take 10–30 seconds. In CI, cache aggressively:

```yaml
# Trivy DB cache (updates every 6 hours on Aqua's end)
- name: Cache Trivy DB
  uses: actions/cache@v4
  with:
    path: ${{ runner.temp }}/trivy-cache
    key: trivy-db-${{ hashFiles('**/Dockerfile') }}-${{ github.run_id }}
    restore-keys: |
      trivy-db-${{ hashFiles('**/Dockerfile') }}-
      trivy-db-

- name: Scan
  env:
    TRIVY_CACHE_DIR: ${{ runner.temp }}/trivy-cache
  run: trivy image --download-db-only && trivy image my-app:${{ github.sha }}
```

For air-gapped environments, pre-seed the DB image using:

```bash
# Pull and mirror the Trivy DB OCI artifact
trivy image --download-db-only
oci-copy \
  ghcr.io/aquasecurity/trivy-db:2 \
  my-registry.internal/security/trivy-db:latest
```

Then point Trivy at the mirror:

```bash
trivy image --db-repository my-registry.internal/security/trivy-db:latest my-app:latest
```

## Severity thresholds and policies

Define a tiered policy rather than blocking on every LOW finding:

| Tier       | Severity          | CI Action                    | SLA                  |
|------------|-------------------|------------------------------|----------------------|
| Block      | CRITICAL          | Fail build, no merge         | Fix before ship      |
| Gate       | HIGH              | Fail build on new findings   | 7-day remediation    |
| Warn       | MEDIUM            | Upload to SARIF, no block    | 30-day remediation   |
| Ignore     | LOW / UNKNOWN     | Suppressed in output         | Best-effort          |

Use `.trivyignore` to suppress accepted/false-positive findings with justification:

```ini
# .trivyignore
# CVE-2023-12345: Not exploitable — package only used in build stage, not runtime
CVE-2023-12345

# CVE-2024-67890: Vendor patch pending — tracked in JIRA-1234, reviewed 2026-08-01
CVE-2024-67890
```

## Anti-patterns

- Scanning without caching the vulnerability DB — causes multi-second cold starts on
  every CI run and can hit rate limits on the DB servers.
- Blocking only on CRITICAL and ignoring HIGH — HIGH CVEs in web-facing services are
  often actively exploited; treat them as blocking for new findings.
- Scanning only at build time, not at deploy time — vulnerability databases update
  continuously; a scan-on-build policy misses CVEs published after the image is built.
  Schedule a nightly re-scan of images in your registry.
- Using `--skip-update` in production CI — this reuses a stale DB and misses recent CVEs.
  Only use `--skip-update` when the DB was freshly downloaded earlier in the same pipeline.
- Not persisting SBOMs — without them you cannot answer "was image X affected by CVE Y"
  retrospectively.

## Gotchas

- Trivy and Grype can report the same CVE as different severities because they use different
  CVSS sources (NVD vs. distro advisories). Distro advisories are usually more accurate for
  the actual risk on that platform. Trivy defaults to distro severity when available.
- Alpine base images have very few OS-level CVEs because Alpine uses musl and BusyBox.
  Most findings will come from language-level dependencies (npm, pip), not the OS layer.
- Scratch-based images (`FROM scratch`) cannot be scanned for OS packages. Scan the build
  stage separately: `trivy image --target build-stage my-app:latest`.
- The `--exit-code 1` flag interacts with `if: always()` in GitHub Actions — make sure your
  SARIF upload step runs even when the scan fails.
- Grype's `--fail-on` threshold applies to the highest severity found across the whole image,
  not just new findings. Use a baseline file (`grype -b baseline.json`) to only flag regressions.

## Verification

```bash
# Confirm Trivy exits non-zero when CRITICAL CVEs present
docker pull ubuntu:20.04
trivy image --severity CRITICAL --exit-code 1 ubuntu:20.04
echo "Exit: $?"   # Should be 1 (old Ubuntu has known CVEs)

# Confirm clean image passes
trivy image --severity CRITICAL --exit-code 1 alpine:3.20
echo "Exit: $?"   # Should be 0

# Validate SBOM is parseable
trivy image --format cyclonedx --output sbom.json alpine:3.20
python3 -c "import json; d=json.load(open('sbom.json')); print(d['bomFormat'])"
# CycloneDX
```

## Related

- supply-chain-security-sbom-slsa.md
- docker-multi-stage-build-optimization.md
- docker-workers-ci-artifacts.md
- github-self-hosted-runners.md

## Sources

- https://trivy.dev/latest/docs/
- https://github.com/aquasecurity/trivy
- https://github.com/anchore/grype
- https://github.com/anchore/syft
- https://docs.github.com/en/code-security/code-scanning/integrating-with-code-scanning/uploading-a-sarif-file-to-github
- https://cyclonedx.org/specification/overview/
