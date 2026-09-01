---
title: "Refund Authority Limits"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Refund Authority Limits

## Purpose

Set the monetary, frequency, and contextual caps within which support personnel may issue refunds or goodwill credits, the approval workflow for amounts or cases that exceed those caps, the justification that must be recorded, and the audit trail that allows the program to be reviewed and the authority to be revoked when it is misused.

## Scope

This article covers refunds, partial refunds, credits (including goodwill credits, service credits, and stored-value credits), waivers of fees, and any other monetary or near-monetary accommodation issued through customer-support channels. It applies whether the accommodation is granted by a human agent, by an automated assistant operating within approved authority, or by an AI-assisted agent. It does not govern refunds issued through formal dispute, chargeback, or regulator channels, which have their own processes, but it does cover any internal approval those processes request from support.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Authority tiers

The company SHOULD define authority tiers that reflect the sensitivity of the action. Tiers SHOULD be expressed in terms of amount per case, amount per customer within a defined window, count of grants within a defined window, category of case (for example, accidental purchase, service outage, defect, accessibility issue, safety issue), and the customer's prior case history. Tiers SHOULD be reviewed at the documented cadence and SHOULD be adjusted in response to sustained changes in case volume, average ticket value, or abuse signals.

A higher tier SHOULD be required for repeat grants to the same customer within a window, for grants tied to a known incident (where a separate incident-credit program may apply), for grants in jurisdictions with strict consumer-protection rules, and for grants issued under pressure (such as during escalation, complaint, or regulator engagement).

## Approval workflow

A grant that exceeds the agent's own authority tier MUST be approved by an agent with the appropriate authority and, where the document specifies, by an independent approver. The approver MUST be different from the requester. Approval MUST be recorded in the case record with the approver's identity, the time of approval, the tier cited, and the rationale. Approval MUST NOT be granted without sight of the underlying case facts. Self-approval, peer approval by an agent without the required tier, or approval after the grant has already been issued MUST be treated as a control failure and escalated.

## Justification

Every grant MUST be accompanied by a justification drawn from an approved taxonomy. The justification MUST identify the customer-visible reason, the evidence (or the absence of evidence where the grant is goodwill), and any incident, complaint, or accessibility reference that bears on the decision. The justification MUST NOT be a generic phrase such as "goodwill," "retention," or "VIP." Where the grant is tied to an incident, the justification SHOULD reference the incident identifier and the credit policy associated with the incident rather than relying on individual discretion.

## Recording

The grant record MUST include the case identifier, the customer identifier (or account identifier, as appropriate), the product or service, the amount, the currency, the timing, the channel through which the customer was notified, the agent and approver identities, the tier cited, the justification code, and a reference to any related case, complaint, or incident. The record MUST be sufficient for audit and reconciliation. Where the grant is delivered through a third-party payment system, the record SHOULD include the payment-system identifier to allow reconciliation.

## Customer communication

The customer MUST be told, in plain language, what they are receiving (refund, credit, fee waiver), the amount and currency, when they can expect it, and any conditions (for example, that a credit applies to future invoices and expires after a period). The communication MUST NOT suggest that the grant is contingent on the customer dropping a complaint or withdrawing a regulator engagement. The customer MUST be given a contact path if the grant does not arrive as described.

## Prohibited patterns

Grants MUST NOT be used as a substitute for fixing a defect, as a substitute for a credit the company is contractually obligated to provide, or as a way to discourage a regulator engagement. Grants MUST NOT be conditioned on the customer's silence. Grants MUST NOT be paid to an account other than the account from which the original payment was made unless a documented exception applies. Repeated grants to the same agent's cases, or grants concentrated in a single queue or shift, MUST trigger a review.

## Audit

The grant program SHOULD be audited for tier compliance, approval independence, justification quality, customer-communication completeness, and reconciliation accuracy. Findings SHOULD feed the support-quality program, the financial-controls program, and the privacy and consumer-protection reviews. Material findings MUST trigger coaching, tier reduction, suspension, or removal of grant authority, and, where the conduct is misconduct, the disciplinary process.

## Canonical sources

- Consumer Financial Protection Bureau, *Consumer rights in financial disputes*, https://www.consumerfinance.gov/compliance/compliance-resources/other-applicable-requirements/consumer-financial-protection-rights/
- PCI Security Standards Council, *PCI DSS Quick Reference Guide*, https://www.pcisecuritystandards.org/document_library/
- AICPA SOC 1 Reporting on an Examination of Controls at a Service Organization, https://www.aicpa.org/topic/soc
- EU Directive 2011/83/EU on consumer rights (as amended), https://eur-lex.europa.eu/eli/dir/2011/83/oj
