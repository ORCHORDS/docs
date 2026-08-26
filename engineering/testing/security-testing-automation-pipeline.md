# Security Testing Automation in CI/CD

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Security testing happens only before releases — a penetration test once a
quarter, a manual code review before launch. Vulnerabilities ship to
production because the feedback loop is too slow. You need security checks
that run on every PR and every build, catching issues at the same speed as
unit tests catch bugs.

## Context

Security testing automation integrates multiple testing techniques into the
CI/CD pipeline so that vulnerabilities are caught before code reaches
production. The 2026 best practice is a layered pipeline: SAST (source code),
SCA (dependencies), secrets detection, container scanning, and DAST (running
application). Each layer catches different vulnerability classes, and no
single tool covers everything.

## The security testing pipeline

```
PR opened → SAST + Secrets scan + SCA
                      ↓
Build → Container image scan + SBOM generation
                      ↓
Deploy to staging → DAST scan
                      ↓
Merge gate: all security checks pass
```

## Layer 1: SAST (Static Application Security Testing)

Analyzes source code without executing it. Catches SQLi, XSS, path
traversal, insecure deserialization, and code-level vulnerabilities.

| Tool | Languages | Best for |
|---|---|---|
| **Semgrep** | 30+ languages | Custom rules, fast, low false positives |
| **CodeQL** | C/C++, C#, Go, Java, JS/TS, Python, Ruby, Swift | GitHub-native, deep dataflow analysis |
| **SonarQube** | 30+ languages | Combined quality + security |
| **Bandit** | Python | Python-specific security linter |

```yaml
# Semgrep in GitHub Actions
- uses: returntocorp/semgrep-action@v1
  with:
    config: >-
      p/owasp-top-ten
      p/javascript
      p/typescript
```

## Layer 2: Secrets detection

Scans code, commits, and config files for accidentally committed secrets
(API keys, passwords, tokens, private keys).

| Tool | Mechanism | Best for |
|---|---|---|
| **Gitleaks** | Git history + file scanning | Pre-commit hook + CI |
| **TruffleHog** | Git history + verified secrets | Detects live/active secrets |
| **GitHub Secret Scanning** | GitHub-native | Push protection (blocks pushes with secrets) |

```bash
# Gitleaks in CI
gitleaks detect --source . --verbose --report-path gitleaks-report.json
```

## Layer 3: SCA (Software Composition Analysis)

Scans dependencies for known vulnerabilities (CVEs).

| Tool | Scope | Best for |
|---|---|---|
| **Grype** | SBOM-based scanning | Pairs with Syft SBOM |
| **Trivy** | Container + filesystem + git | All-in-one scanner |
| **Snyk** | Dependencies + containers + IaC | Developer-friendly, fix suggestions |
| **OSV-Scanner** | OSV database | Google's open-source vuln scanner |
| **npm audit** | npm dependencies | Built-in, zero setup |

## Layer 4: Container image scanning

Scans container images for OS-level vulnerabilities, misconfigurations, and
embedded secrets.

```yaml
# Trivy container scan in CI
- name: Scan container image
  run: trivy image --exit-code 1 --severity HIGH,CRITICAL myapp:${{ github.sha }}
```

## Layer 5: DAST (Dynamic Application Security Testing)

Tests the running application by sending malicious requests and analyzing
responses. Catches runtime vulnerabilities that SAST misses.

| Tool | Type | Best for |
|---|---|---|
| **OWASP ZAP** | Full DAST scanner | Open-source, CI-friendly |
| **Nuclei** | Template-based scanner | Fast, community templates, CVE checks |
| **Burp Suite** | Professional DAST | Manual + automated testing |

```yaml
# ZAP baseline scan against staging
- name: ZAP scan
  uses: zaproxy/action-baseline@v0.12.0
  with:
    target: https://staging.example.com
    fail_action: true
```

## Anti-patterns

- **SAST only** — SAST catches code-level bugs but misses dependency
  vulnerabilities, runtime misconfigurations, and infrastructure issues.
  Layer all five techniques.
- **Blocking on every finding** — start with CRITICAL/HIGH severity as
  merge-blockers. Treat MEDIUM/LOW as warnings. Tune thresholds as the team
  matures.
- **Ignoring false positives** — unmanaged false positives cause alert
  fatigue. Use suppression files (`.semgrepignore`, Trivy `.trivyignore`)
  with documented justification for each suppression.
- **Security team as bottleneck** — developers should own security testing
  results. Security team sets policy and rules; developers fix findings.

## Gotchas

- **SAST false positive rates** — Semgrep and CodeQL have lower false
  positive rates than older SAST tools, but still require tuning. Start
  with curated rulesets (OWASP Top 10) and add custom rules gradually.
- **DAST requires a running environment** — DAST cannot run on PRs alone.
  Deploy to a staging environment and run DAST there.
- **Scan time vs. developer experience** — full DAST scans take 30-60
  minutes. Run lightweight scans (ZAP baseline) on PRs and full scans
  nightly or on release branches.
- **License scanning** — SCA tools often bundle license compliance
  checking. Enable it to catch copyleft license contamination.

## Verification

- Every PR triggers SAST + secrets + SCA scans. Results appear as PR
  status checks.
- Container images are scanned before pushing to the registry.
- DAST runs against staging on every deployment.
- Zero CRITICAL/HIGH findings in the main branch.
- Security findings are triaged within 48 hours (SLA).

## Related

- `documentation/categories/security/owasp-top-10-2025.md`
- `documentation/categories/security/secrets-detection-pre-commit.md`
- `documentation/categories/security/sbom-vulnerability-scanning.md`
- `documentation/categories/devtools/sbom-generation-tools.md`
- `documentation/categories/security/sast-false-positive-management.md`

## Source URLs (verified 2026-08-16)

- Semgrep documentation — https://semgrep.dev/docs/
- CodeQL documentation — https://codeql.github.com/docs/
- Gitleaks — https://github.com/gitleaks/gitleaks
- TruffleHog — https://github.com/trufflesecurity/trufflehog
- OWASP ZAP — https://www.zaproxy.org/
- Nuclei — https://github.com/projectdiscovery/nuclei
