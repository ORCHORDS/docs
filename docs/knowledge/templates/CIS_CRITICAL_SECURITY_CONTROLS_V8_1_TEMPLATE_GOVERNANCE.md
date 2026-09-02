# CIS Critical Security Controls v8.1 Template Governance

## Purpose

The Center for Internet Security (CIS) Critical Security Controls (CIS Controls) v8.1 is a prioritized set of 18 control families designed to mitigate the most prevalent cyber-attacks. A reusable CIS Controls assessment template records, for each Safeguard, the implementation status (IG1, IG2, IG3 maturity), the asset class(es) in scope, the assessment method (automated scan, manual review, observation), the evidence observed, the gap description, and the residual-risk acceptance. The template converts a defensive-control assessment from an implicit posture into an auditable artifact suitable for cyber-insurance diligence, regulatory compliance, and internal gap analysis.

The template must remain generic: it MUST NOT embed real asset inventories, organization names, or specific gap findings that identify a particular deployment.

## Scope

This template applies to the CIS Critical Security Controls v8.1 (2024 update), including the Implementation Group (IG) definitions for small (IG1), medium (IG2), and large (IG3) enterprises. It does not address the prior v7 or v8.0 controls (which use different safeguard numbering); version drift is captured in the template header. The template does not address the CIS Benchmarks (community-developed secure configuration guides); those are governed by a separate template. The template does not cover CIS Hardened Images or CIS-CAT Pro tool output format; a separate import template is required for CIS-CAT results.

## Workflow

1. Open the template and complete the header with the assessment identifier, the version (v8.1), the target Implementation Group (IG1, IG2, or IG3), the assessment date, the scope (asset classes, business units), and the assessor.
2. For each Safeguard (for example 1.1, 5.4, 14.6), populate:
   - Safeguard identifier and title.
   - Implementation Group applicability (IG1, IG2, IG3).
   - Asset class(es) in scope (network devices, endpoints, cloud, applications, data, users).
   - Assessment method: automated scan (with tool and version), configuration review, log review, observation, interview.
   - Evidence observed: configuration snippet, scan output excerpt, log excerpt, policy reference, screenshot.
   - Status: implemented, partially implemented, not implemented, not applicable.
   - Gap description and remediation owner.
3. For each control family (1-18), record the family-level maturity score based on the count and severity of Safeguard-level gaps.
4. Identify controls that are below the target IG; route them to a remediation backlog with owner and target date.
5. Save the completed template alongside the cyber-insurance evidence packet, with access restricted to the security team and the assessor.

## Controls and evidence

- Header records assessment identifier, version, target IG, scope, date, and assessor.
- Per-Safeguard rows record IG applicability, asset class, method, evidence, and status.
- Family-level maturity scorecard summarizes the family results.
- Remediation backlog records owners, target dates, and severity.

## Validation

- Every in-scope Safeguard has a status; no Safeguard is left unaddressed.
- Each "not implemented" or "partially implemented" entry has a remediation owner and target date.
- Family-level scores are mathematically consistent with Safeguard-level statuses.
- The assessment scope (asset classes) is consistent with the asset inventory used for cyber-insurance.
- Scan outputs are reproducible against the same asset inventory.

## Failure correction

Common defects include evaluating only IG1 controls when the target is IG2 or IG3, recording "implemented" without evidence, and aggregating to family-level scores without per-Safeguard justification. Corrective actions include requiring evidence citations for every status, restricting the assessment scope to the actual target IG, and recomputing family-level scores from the per-Safeguard data.

## Limitations

- The template does not substitute for an automated CIS-CAT assessment; it captures the assessment output.
- It does not address CIS Benchmarks compliance; a separate template is required.
- It does not provide scoring against the CIS Community Defense Model; a separate model is required.
- It does not address the mapping to other frameworks (NIST SP 800-53, ISO/IEC 27002); mapping tables are governed by a separate template.

## Scope note

This template is part of the **templates** leaf. Sibling leaves cover: **security** (control selection governance), **standards** (CIS Controls relationships to NIST and ISO), **operations** (remediation backlog maintenance), and **business** (cyber-insurance diligence). The template should be used together with those sibling-leaf articles.

## Canonical sources

- CIS Critical Security Controls v8.1 (Center for Internet Security, 2024): https://www.cisecurity.org/controls/v8-1
- CIS Critical Security Controls v8.0 (Center for Internet Security, 2023): https://www.cisecurity.org/controls/v8
- CIS Implementation Groups (IG1, IG2, IG3) definitions (Center for Internet Security): https://www.cisecurity.org/controls/implementation-groups

Sources were verified on September 1, 2026.
