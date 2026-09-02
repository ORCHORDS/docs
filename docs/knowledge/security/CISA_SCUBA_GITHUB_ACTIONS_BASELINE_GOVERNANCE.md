# CISA SCUBA GitHub Actions Baseline Governance

## Purpose

Govern the application of the CISA SCuBA (Secure Cloud Business Applications) GitHub Actions baseline so that CI/CD GitHub environments meet a defined configuration baseline: the SCuBA secure configuration baselines for GitHub specify the tenant and repository settings that constitute a secure posture, assessable with CISA's assessment tooling.

## Scope

Applies to the studio's GitHub organizations and repositories used for CI/CD. Covers the GitHub Actions-related baseline policies, configuration assessment, and drift remediation. Does not cover application code security (SSDF governs that) or other SaaS platforms' SCUBA baselines.

## Workflow

1. Identify the baseline's policy areas for GitHub: organization and repository settings covering Actions permissions, workflow defaults, runner policies, secret protection, branch protection interplay, and code security settings per the published baseline.
2. Configure the tenant to the baseline: apply each policy's secure setting (e.g., restricting workflow permissions, disabling unnecessary Actions features, enforcing approval for outside collaborators).
3. Assess with CISA's ScubaGear assessment tool: run the assessment against the tenant and record per-policy results — assessment output is the compliance evidence.
4. Remediate findings in priority order: policies marked high-impact first; each remediation verified by re-assessment, not by configuration screenshots alone.
5. Manage exceptions explicitly: any setting deviating from the baseline carries a documented rationale, compensating control, expiry, and owner.
6. Guard against drift: configuration-as-code for org settings where available, plus scheduled re-assessment; GitHub tenants drift through administrative console changes.
7. Extend to repositories: organization-level settings set the floor; repository-level overrides are inventoried and justified against the baseline.

## Controls and evidence

- Baseline policy configuration records per setting.
- ScubaGear assessment output per assessment cycle.
- Remediation records with re-assessment verification.
- Exception register with rationale, expiry, and owners.
- Scheduled re-assessment configuration.

## Validation

- Run the assessment and confirm zero unremediated high-impact findings.
- Sample three exceptions: confirm each has current rationale, compensating control, and expiry.
- Confirm repository-level overrides are inventoried with justification.

## Failure correction

- **Assessment finding unremediated past deadline** → escalate the owner; CI/CD tenant misconfigurations are active attack surface, not paperwork.
- **Drift detected between assessments** → restore baseline configuration, trace the console change, and close the administrative path that bypassed review.
- **Exception expired silently** → remove the exception and apply the baseline setting or re-justify through the register.

## Limitations

- SCuBA baselines target US government-relevant SaaS but apply as strong practice generally; commercial threat models may add requirements beyond the baseline.
- Baselines cover configuration, not code: vulnerable workflows with correct tenant settings remain vulnerable.
- CISA updates baselines as platforms evolve; track baseline versions and re-assess on updates.

## Scope note

This article is part of the security leaf. Cross-reference: `CISA_SCUBA_CLOUD_TENANT_BASELINE_GOVERNANCE.md`, `OWASP_CICD_SEC_2024_GOVERNANCE.md` (operations leaf), and `github/actions-security-hardening.md` (platforms/github).

## Canonical sources

- CISA — SCuBA Secure Cloud Business Applications project: https://www.cisa.gov/scuba
- CISA — GitHub Actions Secure Baseline (SCuBA): https://github.com/cisagov/ScubaGear
- CISA — ScubaGear assessment tool: https://github.com/cisagov/ScubaGear
- GitHub — Security hardening for GitHub Actions: https://docs.github.com/en/actions/security-for-github-actions/security-guides/security-hardening-for-github-actions
- NIST SP 800-218 — Secure Software Development Framework: https://csrc.nist.gov/pubs/sp/800/218/final
