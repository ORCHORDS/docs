> Auto-generated from `Security Scan.md` in the docs repo.

> Auto-generated from `Security Scan.md` in the docs repo.

> Auto-generated from `Security Scan.md` in the docs repo.

> Auto-generated from `docs/engineering/workflows/SECURITY_SCAN.md` in the docs repo.

---
title: "security-scan.yml Workflow"
version: "1.0.0"
last-updated: "2026-06-21"
owner: "maya.rodriguez (Backend Lead) — security policy; mike.johnson (DevOps) — CI integration"
status: "approved"
iso-refs: ["ISO/IEC 27001:2022 A.8.24", "ISO/IEC 27002:2022 A.8.28", "ISO/IEC 25010:2023 (Security)"]
related-workflow: ".forgejo/workflows/security-scan.yml"
---

# security-scan.yml — Secret Scan + SAST on PR

**Project:** Beetle Studio
**Owner:** Maya Rodriguez (Backend Lead) — security policy, severity thresholds; Mike Johnson (DevOps Lead) — CI integration
**Reviewers:** Kirk Beka (CTO), Sarah Miller (Build & Release Engineer)
**ISO Standards:** ISO/IEC 27001:2022 A.8.24 (Use of cryptography), ISO/IEC 27002:2022 A.8.28 (Secure coding), ISO/IEC 25010:2023 (Security subcharacteristic)
**Source file:** `beetle-studio/beetle-studio/.forgejo/workflows/security-scan.yml` (1,795 bytes, 2 jobs)
**Last Reviewed:** 2026-06-21

---

## Scope & Audience

| Aspect | Definition |
|---|---|
| **Scope** | Gitleaks secret scan + Semgrep SAST on every PR to `main` that touches source / tests / build files |
| **Diátaxis form** | Reference |
| **Primary audience** | Maya Rodriguez, Mike Johnson, all engineers |
| **Secondary audience** | Security audit; third-party compliance reviewers |

---

## Purpose

Detects hard-coded secrets and common C/C++ security defects before merge. Both jobs are **advisory** — they `exit 0` regardless of findings. The signal is intended for human review of the Actions log; the actual gating is performed by code review and by the rules in [`docs/security/WAIVERS.md`](../../security/WAIVERS.md) for accepted-risk findings.

> **Status as of 2026-06-21:** the security-scan jobs are not required checks. To make them required, a follow-up is to add a `severity: high` filter to gitleaks, and to make semgrep fail on `error`-level findings. The work is tracked separately.

## Trigger

| Event | Filter |
|---|---|
| `pull_request` | `branches: [main]`, `paths: ['src/**', 'tests/**', 'CMakeLists.txt']` |

A PR that only changes docs, build artifacts, or configuration files will not trigger this workflow. This is intentional — secret leaks in documentation are still flagged in PR review, but the scanner is restricted to the code surface.

## Concurrency

| Group | Behavior |
|---|---|
| `security-scan-${{ github.event.pull_request.number }}` | `cancel-in-progress: true` |

## Jobs

### 1. `gitleaks`

| Aspect | Value |
|---|---|
| Runner | `ubuntu-latest` |
| Timeout | 5 minutes |
| Tool | gitleaks v8.21.2 (downloaded from GitHub releases; installed to `/usr/local/bin/`) |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `actions/checkout@v4`, `fetch-depth: 1` |
| 2 | Run gitleaks | Installs gitleaks if missing; runs `gitleaks detect --source . --no-banner --no-git --config .gitleaks.toml` (if a config exists) |

> **Note on `--no-git`:** The `--no-git` flag is intentional. It forces gitleaks to scan the working tree as plain files (using its native scanner) rather than walking the git history. This is faster on shallow clones and avoids noise from old commits. If a deep audit is needed, a separate nightly job should run without `--no-git`.

The job is wrapped in `set +e`; findings appear in the log but do not block the PR.

### 2. `semgrep`

| Aspect | Value |
|---|---|
| Runner | `ubuntu-latest` |
| Timeout | 8 minutes |
| Tool | semgrep (`pip3 install semgrep` if missing) |

#### Steps

| # | Step | Purpose |
|---|---|---|
| 1 | Checkout | `actions/checkout@v4`, `fetch-depth: 1` |
| 2 | Run semgrep | Runs `semgrep scan --config auto --exclude='third_party' --exclude='scripts' --exclude='benchmarks' --timeout=180 .` |

`--config auto` lets semgrep pick its public registry of community rules. The 180-second per-rule timeout prevents one slow rule from blocking the job.

Like gitleaks, the job is advisory and exits 0.

## Configuration

### Secrets

None used. The scanner does not call any external API at runtime. (Semgrep's `auto` config fetches rules from the Semgrep registry at job start; this requires network egress from the runner.)

### Environment variables

None explicit.

### Tool Configuration Files

| File | Used by | Purpose |
|---|---|---|
| `.gitleaks.toml` | gitleaks | Custom allow-list / extended rules beyond the built-ins |
| `.semgrep.yml` (or `semgrep-rules/`) | semgrep | Local rule overrides — currently not in the repo; semgrep runs with `--config auto` only |

A follow-up should commit `.semgrep.yml` with the project-specific rules (e.g., forbid `strcpy`, `sprintf`, `gets`; require RAII over raw `new`/`delete`; flag `srand(time(NULL))` for cryptographic randomness).

## Severity Thresholds

The workflow does not currently enforce thresholds. The intended model (per `SECURITY_POLICY.md` and the waivers process):

| Severity | Action |
|---|---|
| **Critical** (e.g., AWS key in source, hard-coded password, `strcpy` on user input) | Block merge; ping `@security-team`; create incident ticket |
| **High** (e.g., weak hash function, missing input length check) | Block merge; reviewer can override with a written waiver in `WAIVERS.md` |
| **Medium** | Warn; allow merge; open ticket automatically |
| **Low** | Log only; no action |

The waivers file is `docs/security/WAIVERS.md`, owned by Maya Rodriguez, reviewed quarterly. (See that file for the current waiver list.)

## Known Limitations

- **Advisory only.** The workflow does not block merge. To convert to blocking, replace `exit 0` with a real exit-code check, and add the workflow to branch protection's "Required Checks" list.
- **No SBOM or SCA.** This workflow scans code for secrets and patterns, not third-party dependencies. vcpkg and FFmpeg are not scanned. A future job should add `vcpkg audit` (for C++ deps) and `npm audit` (for the Electron-adjacent tooling, even though Beetle Studio is C++/Win32 native).
- **No DAST.** The application is a desktop app, not a web service; DAST in the traditional sense does not apply. A future enhancement is fuzzing the binary inputs (e.g., project files, audio/video streams) with libFuzzer + AFL.
- **Semgrep `--config auto` is registry-dependent.** If the Semgrep registry is unavailable, the job will produce no findings. Pin a local rule set to make the scan deterministic.
- **Gitleaks `--no-git` misses historical leaks.** Old commits that contain a secret will not be caught. A nightly job should run `gitleaks detect --no-banner` (without `--no-git`) on the full history.
- **No Microsoft-specific rules.** The scanner uses generic CWE rules; Win32-specific patterns (e.g., unsafe `WinExec` use, `LoadLibrary` with untrusted paths) are not in the default rule set. Add custom rules.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| gitleaks not installed | Download from GitHub releases was blocked by network policy on the runner | Self-host gitleaks; or vendor the binary in `third_party/` |
| gitleaks reports a known false positive | The secret pattern matched a placeholder value (e.g., `EXAMPLE_KEY=abc123`) | Add an allow-list rule in `.gitleaks.toml` |
| semgrep is slow | `--config auto` downloads many rules; 8-minute timeout hit | Pin a local rule set; reduce rule set size; bump timeout to 15 |
| Workflow does not run | Path filter excluded the change | Touch `src/**`, `tests/**`, or `CMakeLists.txt` |
| Findings shown but PR is merged | Advisory mode | This is by design; the team relies on code review to catch findings |

## References

### Internal Documents

- [CI/CD Pipeline Overview](../CI_CD_PIPELINE.md)
- [Security Policy](../../SECURITY_POLICY.md)
- [Security Waivers](../../security/WAIVERS.md)
- [Threat Model (planned)](../../security/THREAT_MODEL.md)
- [Vulnerability Disclosure (planned)](../../security/VULNERABILITY_DISCLOSURE.md)

### External

- gitleaks — https://github.com/gitleaks/gitleaks
- semgrep — https://semgrep.dev/
- OWASP Top 10 2021 — https://owasp.org/Top10/
- CWE Top 25 — https://cwe.mitre.org/top25/
- ISO/IEC 27001:2022 A.8.24 — Use of cryptography
- ISO/IEC 27002:2022 A.8.28 — Secure coding
- ISO/IEC 25010:2023 — Security subcharacteristic
- Forgejo Actions reference — https://forgejo.org/docs/latest/user/actions/reference/

---

*Grounded in: ISO/IEC 27001:2022 A.8.24, ISO/IEC 27002:2022 A.8.28, ISO/IEC 25010:2023 (Security). Workflow source-of-truth: `beetle-studio/beetle-studio@.forgejo/workflows/security-scan.yml`.*
