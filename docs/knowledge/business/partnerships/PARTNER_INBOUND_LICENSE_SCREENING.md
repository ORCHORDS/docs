# Partner Inbound License Screening

When a partner contributes code, libraries, designs, or documentation to a joint offering, the contribution arrives under a licence that travels with it. Inbound licence screening is the review that determines what those licences permit, whether copyleft obligations attach, whether they are compatible with the intended distribution model, and what to do when they are not. This article defines the screening workflow, the compatibility triage, and the upgrade paths for constrained components.

## Scope

Covers licences under which partner-contributed material enters the organisation: open-source licences detected in partner code drops, custom inbound licences on partner proprietary components, and dual-licence or commercial open-source terms. In scope: licence identification, copyleft detection, compatibility triage against intended outbound terms, remediation and upgrade paths, and recordkeeping. Out of scope: the organisation's own outbound licensing and any decision to publish jointly developed code as open source, which is a separate governance question. The accountable role is the **inbound licence screener**, with escalation to counsel for copyleft conflicts and ambiguous terms.

## Workflow or implementation guidance

Begin with identification, not assumption. Run licence scanning across every partner contribution drop and treat unlabelled files as unidentified until scanned. Scan output must record component name, version, detected licences, and licence text location within the drop. Where the partner asserts a licence that differs from what scanning detects — a declared MIT header above GPL-licensed code, for instance — the detected evidence governs the triage until the partner reconciles it.

Classify each detected licence by obligation profile. Permissive licences (MIT, BSD-2, BSD-3, ISC, Zlib, Apache-2.0) carry attribution and notice duties and, in Apache-2.0's case, patent and state-changes provisions; they rarely conflict with proprietary distribution. Weak copyleft licences (MPL-2.0, LGPL-2.1, LGPL-3.0, EPL-2.0) confine source-sharing duties to the covered files or the linked component, and are usually workable with file-level separation. Strong copyleft licences (GPL-2.0, GPL-3.0, AGPL-3.0) extend source obligations to derivative works under linking and derivative-work tests that vary by licence and jurisdiction; network copyleft under AGPL reaches software merely offered over a network. This tier determines everything downstream.

Triage against the intended outbound model. Build a small compatibility matrix: intended distribution model (proprietary binary, SaaS, on-premises appliance, source-available) against each licence class. A proprietary outbound model plus strong copyleft inbound is a conflict unless the covered component is isolated as an independent work communicating at arm's length, or a commercial licence replaces the open-source one. An SaaS model plus AGPL is a conflict unless the component is fully decoupled. Record the triage conclusion and its reasoning per component, because linking and derivative-work analyses are fact-specific and will be re-examined under dispute.

Escalate conflicts through defined routes rather than improvising. Options, in the order most partners prefer: request a replacement component under a compatible licence; purchase the commercial licence the same project often sells; refactor to remove the dependency; isolate the component behind a process or network boundary that satisfies independence; or accept the obligation and plan to publish the affected scope. Each route needs an owner, a cost estimate, and a deadline.

Pursue upgrade paths deliberately. When a partner component is acceptable only under a newer licence version — MPL-1.1 to MPL-2.0, EPL-1.0 to EPL-2.0, or GPLv2-only to a compatible later grant — confirm the upgrade is actually available: copyright holders must have granted the later version, and a project relicensed may require contributor consent already gathered. Document the version pin and the licence that applies to the exact pinned version, since licence text can change between minor releases of the same project.

Close each drop with a screening decision record: identified components, licences, triage outcomes, conflicts, remediation chosen, and conditions on the partner for future drops.

## Controls

- Mandatory scan gate: no partner drop merges into the joint build without a screening decision record, including drops the partner labels trivial.
- Compatibility matrix maintained as a controlled document, reviewed when the outbound model changes.
- Conflict escalation register with named owners, routes, deadlines, and resolution evidence.
- Version-pin register binding each component to the exact version and licence text reviewed, refreshed on every dependency bump.
- Notice and attribution inventory assembled per release so permissive-licence duties are executed, not merely noted.
- Partner contract clause requiring contribution warranties: the partner declares licences for contributed material and notifies on change.
- Periodic re-screen of the dependency tree, because transitive dependencies arrive without the partner's knowledge and carry their own licences.

## Validation evidence

The screening programme produces scan reports tied to drop identifiers, screening decision records, the compatibility matrix with change history, the escalation register with resolutions, version-pin registers, and attribution inventories shipped with releases. Validate by sampling three components in the joint build and tracing each to its pin register entry and licence text; then sample the reverse direction — pick three detected licences in the latest scan and confirm each has a decision record, including "no action required" outcomes. Reconcile the shipped attribution inventory against the permissive-licence set from the scan; missing notices are the most common silent failure of an otherwise sound programme. Retain superseded decisions when a component is replaced, since shipped releases remain governed by the licences they shipped under.

## Failure modes and correction

Common failures: scanning only first-level dependencies and missing transitive copyleft; treating a partner's licence declaration as authoritative over contradictory file headers; resolving a GPL conflict informally in a meeting without recording the isolation architecture; accepting a component whose commercial licence expires mid-relationship without renewal terms; and re-screening lapsing after organisational change. Correct by deep-scanning the full tree, reconciling declarations with evidence in writing, documenting isolation boundaries in the architecture record, and adding renewal terms to the partner agreement. Where shipped releases already carry an unmet obligation, quantify exposure with counsel, publish the affected scope or negotiate a cure with the copyright holder, and record the decision; quiet removal in a later release does not cure earlier distribution.

## Limitations

Derivative-work and linking analyses are jurisdiction- and fact-dependent; screening outcomes are risk assessments, not legal determinations. Scanner coverage is incomplete for custom licences, minified code, and vendored copies, so human review remains necessary for partner-proprietary material. Dual-licence and commercial open-source terms change between versions and require per-version review. This article is operational guidance and does not substitute for legal review of any specific conflict.

## Canonical sources

- SPDX — License list maintained by the Linux Foundation: https://spdx.org/licenses/
- Open Source Initiative — Licenses by category: https://opensource.org/licenses
- Free Software Foundation — Licenses: https://www.gnu.org/licenses/
- U.S. Copyright Office — Circular on copyrighted software: https://www.copyright.gov/circs/circ61.pdf
