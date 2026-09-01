# OWASP Cloud-Native Top 10 Governance

## Purpose

The OWASP Cloud-Native Application Security Top 10 is a community-maintained awareness document that identifies the highest-impact security risks specific to cloud-native systems: containers, orchestration, serverless functions, service meshes, declarative APIs, and CI/CD pipelines. It is not a control catalog, but it provides a priority list that organizations use to focus threat modeling, security testing, and secure-default work.

## Scope

The Top 10 applies to systems that use any combination of containers, Kubernetes-class orchestrators, serverless runtimes, declarative configuration as code, and CI/CD pipelines. It complements — and does not replace — the broader OWASP Top 10 (web-application risks), NIST SP 800-204 (cloud-native security strategies), and CNCF security guidance.

## How the list is used

The Top 10 is a triage tool, not a checklist of equal-priority items. The list is consumed as follows:

- map each in-scope service to the risks that actually apply (not every risk applies to every service);
- for each applicable risk, identify the mitigations already in place and the mitigations that are missing;
- prioritize missing mitigations by risk severity and by exposure, not alphabetically;
- re-evaluate after each significant service change.

## Engineering workflow

1. Inventory the cloud-native substrate: orchestrator, registry, CI/CD, runtime, service mesh, identity plane.
2. Map each substrate component to the risks in the Top 10 that genuinely apply.
3. For each applicable risk, list the existing mitigations and the evidence backing them.
4. For each missing mitigation, capture it as a backlog item with an owner and a target date.
5. Re-exercise the mapping when OWASP updates the list, when the substrate changes, or after an incident.

## Controls and evidence

- A risk-to-substrate matrix keyed to the current OWASP Top 10 list.
- Mitigation evidence per row: configuration exports, scan reports, policy manifests, audit logs.
- Backlog of missing mitigations with owners and dates.
- Review log signed by platform, security, and application owners.

## Validation

- Independent reviewer walks the matrix against the running substrate.
- Periodic red-team or purple-team exercises test at least one mitigation per applicable risk.
- Configuration scans re-baseline against the matrix after every release.

## Failure modes and corrections

- Treating the Top 10 as a compliance checklist of equal-weight items — correct by prioritizing the risks that apply, not by ticking every row.
- Skipping risks that are not in the current list — correct by combining the Top 10 with NIST SP 800-204 and CNCF guidance rather than substituting one for the other.
- Letting one team own all rows — correct by distributing the matrix across platform, security, and application teams.
- Failing to re-run the mapping after a substrate change — correct by hooking the mapping to platform-release process.

## Risk categories covered

The cloud-native list concentrates on risks that arise from the substrate rather than from application logic. Representative categories include insecure cloud, container, or orchestration configurations; supply-chain failures in images and dependencies; overly permissive identity and access; weak workload isolation; insecure APIs between internal services; inadequate logging and monitoring; misuse of serverless runtime features; secrets mishandling; and unhardened CI/CD pipelines. Because the list is periodically revised, teams must pin the version they are working against and record the revision date in the matrix header.

## Scoring and prioritization

Because the Top 10 is a ranking of prevalence and impact, organizations should not treat row order as their own priority order. Local prioritization should combine:

- exposure (public internet-facing vs. internal-only);
- blast radius (data sensitivity, tenant isolation boundary, shared platform components);
- existing compensating controls; and
- cost and disruption of remediation.

A risk that is top-of-list but sits behind strong compensating controls can reasonably rank below a lower-listed risk with no compensating control, provided the reasoning is written down.

## Integration with platform change management

The matrix is only useful if it is consulted when changes are proposed. Practical integration points include:

- the platform change template requires the author to list the Top 10 rows affected by the change;
- the reviewer confirms that the mitigations listed for those rows remain valid after the change;
- a new runtime feature (for example, enabling a service mesh, adding a sidecar, or opening a new ingress path) triggers a re-triage of the affected rows;
- the security review gate samples the matrix rows with the weakest evidence before approving a change.

This turns the awareness document into a durable input to engineering decisions rather than a static artifact that security updates alone.

## Reporting

Report the matrix upward in a form leadership can act on:

- count of applicable risks per service, with the count of mitigations verified;
- top missing mitigations ranked by exposure and blast radius, each with an owner and target date;
- trend over time of verified mitigations versus missing mitigations;
- exceptions granted, with expiry dates and approvers.

## Limitations

- The Top 10 is a community list, not a standard; changes between versions can be significant.
- It is intentionally short and cannot enumerate every cloud-native risk; teams should pair it with deeper guidance.
- It is not a substitute for control catalogs such as NIST SP 800-53 or ISO/IEC 27002.
- It does not address legacy or non-cloud-native systems.

## Canonical sources

- OWASP Foundation (OWASP, primary authority) — Cloud-Native Application Security Top 10: https://owasp.org/www-project-cloud-native-application-security-top-10/
- OWASP Foundation (OWASP, primary authority) — Top 10 Web Application Security Risks: https://owasp.org/www-project-top-ten/

## Scope note

This article summarizes project-neutral use of the OWASP Cloud-Native Top 10. It does not claim that any specific system has addressed every risk in the list.