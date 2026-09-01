# EU Product Liability Directive Software and AI Evidence

**Issue:** Software, AI-enabled products, digital manufacturing files, and post-market updates can affect product-liability exposure, but engineering and legal evidence is fragmented or retained only for operational convenience.

**Date:** 2026-09-01
**Author:** ORCHORDS
**Status:** documented

## Public legal context

Directive (EU) 2024/2853 modernizes the EU product-liability framework. The official EUR-Lex record states that it entered into force on 8 December 2024 and requires Member States to transpose it by 9 December 2026. National implementation and the Directive's temporal rules must be assessed before deciding which regime applies to a specific product or claim.

At a high level, the Directive expressly addresses software and digital product behavior, including changes associated with updates and learning capabilities. It also introduces mechanisms concerning access to relevant evidence and evidentiary presumptions in defined circumstances. These mechanisms do not make every software defect a compensable product defect, and they do not replace fact-specific legal analysis.

## Control objective

Maintain proportionate, reproducible evidence showing what product was supplied, which software and model versions affected its behavior, what safety expectations and warnings were communicated, what changed after release, and how reported harm or alleged defect was investigated.

## Evidence model

For each released product or materially distinct configuration, retain:

- responsible economic operator and product-family identifiers;
- release, firmware, software, model, data, and safety-critical configuration versions;
- intended use, reasonably foreseeable use considered, limitations, warnings, and user instructions;
- design, verification, validation, risk, security, accessibility, and human-factors decisions relevant to safety;
- component and supplier provenance sufficient to investigate a reported defect;
- update eligibility, rollout, rollback, support status, and end-of-support communications;
- post-market reports, complaint classification, incident investigation, corrective actions, and closure rationale; and
- preservation, access-control, legal-hold, disclosure-review, and deletion decisions.

Use stable identifiers so a complaint, device, installation, update event, and supporting artifact can be reconciled without exposing unnecessary personal data.

## Software and AI change control

A post-market change can alter product behavior. Classify each update, model replacement, parameter change, rules change, safety-control change, or data-dependent behavior change for potential safety impact before release.

The change record should identify:

1. the previous and proposed behavior;
2. affected products, users, interfaces, and dependencies;
3. new or changed hazards and mitigations;
4. verification and representative test evidence;
5. rollout monitoring and stop conditions;
6. rollback feasibility and residual risk; and
7. approval by accountable engineering, product, safety, and legal roles as appropriate.

Do not overwrite evidence for a prior version with current-state documentation. Preserve the historical state needed to reconstruct what was supplied and what the producer controlled at the relevant time.

## Claim and incident workflow

1. Preserve relevant records without altering original artifacts.
2. Separate immediate safety response from conclusions about defect, causation, or liability.
3. Identify the product, claimant context, event time, applicable versions, update history, and alleged damage.
4. Create a privilege-aware investigation plan with qualified counsel where needed.
5. Reproduce behavior in a controlled environment when safe and proportionate.
6. Assess supplier, integration, deployment, maintenance, misuse, alteration, and post-supply factors without assuming any one cause.
7. Record corrective-action and communication decisions consistently across safety, support, insurance, and regulatory channels.
8. Review any evidence request for relevance, confidentiality, trade-secret, security, personal-data, and procedural requirements before disclosure.

## Disclosure readiness

Evidence should be findable and explainable, not merely retained. Maintain a data map, artifact owners, integrity controls, export procedures, redaction process, and review log. Test retrieval using a fictional incident so teams can locate the correct historical versions without relying on production credentials or personal data.

Do not destroy or silently rewrite records after a complaint, incident, preservation notice, or reasonably anticipated dispute. Retention and legal-hold rules require jurisdiction-specific advice.

## Verification

- Reconstruct a sampled release and its safety-relevant updates from immutable or integrity-protected records.
- Trace a fictional complaint to the exact product, software, configuration, warnings, and corrective-action decision.
- Confirm that historical model and test evidence remains distinguishable from the current version.
- Exercise a scoped evidence export with legal, privacy, security, and trade-secret review.
- Verify that suppliers and processors can provide contractually required evidence within the planned response time.

## Failure modes

- Treating software as outside product-liability evidence creates a gap between product behavior and release records.
- Retaining only the latest documentation prevents reconstruction of the supplied version.
- Assuming compliance or successful testing proves absence of defect confuses different legal questions.
- Treating an evidence-disclosure mechanism as unrestricted access can expose unrelated personal, confidential, or security-sensitive material.
- Changing logs or incident records during investigation undermines integrity and credibility.
- Applying the Directive without checking national transposition, timing, scope, and conflict-of-law questions overstates the legal conclusion.

## Official source

- [Directive (EU) 2024/2853 on liability for defective products](https://eur-lex.europa.eu/eli/dir/2024/2853/oj)

Source status and dates were checked on September 1, 2026.

## Scope note

This article provides operational evidence guidance, not legal advice. Applicability, duties, disclosure, presumptions, limitation periods, recoverable damage, and national procedure require qualified counsel and the applicable Member State law.
