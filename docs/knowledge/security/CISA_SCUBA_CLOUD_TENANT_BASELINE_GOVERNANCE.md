# CISA SCuBA Cloud Tenant Baseline Governance

## Purpose

This guide describes a governance model for applying the Cybersecurity and Infrastructure Security Agency's Secure Cloud Business Applications (SCuBA) security baselines to cloud tenants.

Binding Operational Directive 25-01 requires United States Federal Civilian Executive Branch (FCEB) agencies to implement specified secure cloud configurations. Organizations outside the FCEB may voluntarily use the directive, SCuBA baselines, assessment tools, and reporting practices as a security framework. Voluntary adoption does not make the directive legally binding on those organizations.

The objective is not merely to pass a one-time configuration check. Effective governance maintains an authoritative tenant inventory, assesses applicable controls, remediates weaknesses, records justified deviations, and continuously produces evidence that configurations remain effective.

## Current context/status

CISA issued BOD 25-01 on December 17, 2024, and the directive remains in effect. Its binding scope is FCEB agencies.

The directive established these historical implementation deadlines:

| Milestone | Deadline |
|---|---:|
| Complete the cloud tenant inventory | February 21, 2025 |
| Deploy assessment tooling and enable continuous reporting | April 25, 2025 |
| Implement mandatory secure configurations | June 20, 2025 |

These dates remain relevant when evaluating an agency's implementation history, but governance should now focus on sustained compliance, configuration drift, newly acquired tenants, baseline changes, and unresolved findings.

CISA publishes required configurations and supporting SCuBA resources separately. A team must confirm the current status of each baseline before treating it as mandatory or production-ready. Final Microsoft 365 baselines should be distinguished from baselines labeled draft, under development, or otherwise non-final. For example, a Google Workspace baseline must not be represented as a final requirement unless CISA's current publication explicitly gives it that status.

Record the baseline version, publication status, retrieval date, applicable service, and originating CISA page in the control register.

## Governance workflow and controls

### 1. Establish ownership

Assign accountable owners for:

- cloud tenant inventory;
- baseline interpretation and control mapping;
- identity and privileged access;
- service-specific configuration;
- evidence collection and reporting;
- exceptions and risk acceptance;
- remediation tracking; and
- baseline-change monitoring.

Security teams may coordinate the program, but service owners must remain responsible for the configurations they operate. Internal audit or an independent assurance function should periodically test whether reported results match the actual tenant state.

### 2. Maintain an authoritative tenant inventory

Inventory every in-scope production, development, test, pilot, acquired, and legacy tenant. Include tenants administered by contractors or business units rather than only those centrally managed.

For each tenant, record at least:

- tenant identifier and service provider;
- business purpose and data sensitivity;
- production status;
- owning organization and technical contacts;
- identity provider and authentication boundary;
- licensing or service tier relevant to control availability;
- privileged administrative roles and emergency accounts;
- approved integrations and external administrators;
- applicable baseline and baseline version;
- assessment status; and
- planned retirement or consolidation date, if any.

Reconcile the inventory against procurement records, identity-provider registrations, finance data, domain and DNS records, security telemetry, and provider administration portals. Discovery differences must become tracked issues rather than informal notes.

New tenants should enter governance before they store organizational data or support production activity.

### 3. Determine applicability

Map each published requirement to the tenant and classify it as:

- applicable and implemented;
- applicable and not implemented;
- implemented through an approved compensating control;
- not applicable with documented rationale;
- temporarily deviated under approved risk acceptance; or
- pending assessment.

Do not classify a control as inapplicable solely because a required feature is inconvenient, unlicensed, or incompatible with an existing workflow. Such conditions require remediation planning, an architectural decision, or formal risk treatment.

Preserve the source requirement identifier so results remain traceable to CISA's required configurations and the relevant SCuBA baseline.

### 4. Assess configuration state

Use CISA-supported or otherwise approved assessment tooling where appropriate, while recognizing that automated checks do not replace governance review.

Assessment controls should:

1. run with read-only or least-privileged permissions where possible;
2. identify the tenant, tool version, baseline version, and collection time;
3. protect collected configuration data as potentially sensitive;
4. produce machine-readable results suitable for comparison over time;
5. distinguish collection errors from failed controls; and
6. retain sufficient detail to reproduce or independently validate findings.

Manually evaluate controls that cannot be reliably assessed through available interfaces. Document the test procedure, evidence examined, result, reviewer, and date.

### 5. Remediate findings safely

Prioritize findings based on exposure, exploitability, affected identities and data, external accessibility, and the role of the affected service.

Use controlled change procedures:

- identify the intended secure state;
- test user and service impact;
- plan rollback and emergency access;
- obtain required approvals;
- implement through auditable administration or configuration-as-code;
- verify the resulting tenant state; and
- close the finding only after evidence confirms the change.

High-impact identity changes should be staged carefully. Do not weaken controls broadly to resolve isolated compatibility problems.

### 6. Govern privileged roles

Privileged-role governance should include:

- a minimal number of permanently assigned administrators;
- separate administrative and ordinary-use identities;
- phishing-resistant authentication where applicable;
- time-bound or just-in-time elevation when supported;
- approval and logging for privileged activation;
- protected, monitored emergency-access accounts;
- periodic role recertification;
- restrictions on third-party and cross-tenant administration; and
- alerts for role grants, policy changes, and security-control disablement.

The identities and automation accounts used for assessment and reporting must also be reviewed. A compliance collector must not become an unmonitored privileged backdoor.

### 7. Produce continuous evidence

Continuous reporting should detect drift rather than repeatedly reproduce an obsolete snapshot. Establish assessment frequencies based on risk and supplement scheduled scans with event-driven checks after major changes.

Retain:

- tenant inventory snapshots;
- assessment outputs and collection logs;
- control mappings and applicability decisions;
- remediation tickets and verification results;
- privileged-role reviews;
- deviation approvals and expiry dates;
- evidence of reporting delivery; and
- baseline-version change records.

Dashboards should separate compliant controls, true failures, unassessed controls, unsupported checks, expired evidence, and collection failures.

### 8. Manage baseline updates

Monitor CISA's directive, required-configuration, and SCuBA project pages for revisions. When a baseline changes:

1. record the new version and publication status;
2. compare it with the version currently implemented;
3. identify added, removed, and changed requirements;
4. assess operational and security impact;
5. assign implementation owners and dates;
6. update assessment logic and control mappings; and
7. preserve historical results under their original baseline version.

A draft baseline may be evaluated in a sandbox or used as advisory guidance, but it should not silently replace a final baseline or be reported as a binding requirement.

### 9. Control deviations and risk acceptance

Every deviation should identify:

- affected tenant and control;
- reason the secure configuration cannot currently be used;
- security impact and affected assets;
- compensating controls;
- accountable risk owner;
- approval date and expiration;
- remediation plan; and
- review cadence.

Exceptions must be time-bound. Expired exceptions should automatically return to review and should not be treated as compliant. FCEB agencies must also follow any CISA-specific reporting or deviation process applicable to the directive.

## Failure modes

Common governance failures include:

- omitting test, acquired, or contractor-managed tenants from inventory;
- reporting tool execution as evidence of compliance despite collection errors;
- using stale or unofficial baseline copies;
- treating draft guidance as a final CISA requirement;
- marking controls inapplicable to avoid licensing or operational changes;
- granting excessive privileges to assessment tooling;
- accepting risks without owners, expiry dates, or compensating controls;
- closing findings before post-change verification;
- failing to reassess after baseline or tenant changes;
- losing visibility when APIs, credentials, or reporting pipelines fail; and
- measuring only an aggregate compliance percentage that hides critical identity failures.

Controls should fail visibly. Missing evidence, incomplete collection, and unsupported tests must produce an unknown or unassessed state, not a passing result.

## Evidence and review

Review the program at a defined cadence and after significant incidents, acquisitions, tenant migrations, baseline updates, or identity-architecture changes.

At minimum, reviewers should be able to determine:

- whether the tenant inventory is complete;
- which baseline and version apply to each tenant;
- whether each control has current evidence;
- whether assessment failures are distinguishable from control failures;
- which findings remain open and why;
- whether privileged roles were recertified;
- whether deviations are valid and unexpired; and
- whether reported status can be reproduced from retained evidence.

For FCEB agencies, internal governance supplements rather than replaces directive-specific reporting and CISA oversight obligations.

## Sources

- [BOD 25-01: Implementing Secure Practices for Cloud Services](https://www.cisa.gov/news-events/directives/bod-25-01-implementing-secure-practices-cloud-services)
- [BOD 25-01 Required Configurations](https://www.cisa.gov/resources-tools/services/bod-25-01-implementing-secure-practices-cloud-services-required-configurations)
- [Secure Cloud Business Applications (SCuBA) Project](https://www.cisa.gov/resources-tools/services/secure-cloud-business-applications-scuba-project)
- [CISA announcement of BOD 25-01, December 17, 2024](https://www.cisa.gov/news-events/alerts/2024/12/17/cisa-issues-bod-25-01-implementing-secure-practices-cloud-services)

## Scope note

This article is project-neutral governance guidance, not legal advice or an authoritative substitute for CISA instructions. BOD 25-01 binds FCEB agencies. Other public- and private-sector organizations may adopt its practices voluntarily. Always verify baseline status, required configurations, reporting instructions, and revisions directly with CISA before making compliance claims.
