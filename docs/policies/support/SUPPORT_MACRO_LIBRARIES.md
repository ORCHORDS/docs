---
title: "Support Macro Libraries"
owner: "Support Lead"
status: "approved"
classification: "public"
last-reviewed: "2026-08-22"
review-cycle: "90 days"
next-review: "2026-11-20"
---

# Support Macro Libraries

## Purpose

Govern the creation, review, approval, expiration, and retirement of pre-approved support response macros — canned text, response templates, quick-reply blocks, and similar reusable language — so that macros are accurate, current, accessible, and consistent with policy, and so that their use does not displace the case-specific thinking the support process depends on.

## Scope

This article covers every pre-approved response macro available to support agents and AI-assisted agents across all channels, including chat, email, voice (read-aloud scripts), messaging, and in-app help. It covers macros written by the support team, by other internal teams for support use, and by AI-assisted drafting when the output is preserved as a macro for reuse. It does not cover personal agent drafts or agent-specific saved text that has not been promoted to the shared library.

## Requirements

This article sets the following obligations for the covered support activity. MUST/SHOULD/MAY statements throughout the body of this article are part of these requirements.


## Approval workflow

A macro MUST NOT enter the shared library without documented approval. The approval workflow MUST include:

- authorship and the team responsible for ongoing ownership;
- a content review for accuracy against current policy, product behavior, and the law;
- a privacy review where the macro references personal data or sensitive categories;
- a security review where the macro instructs the customer to take a security-sensitive action;
- an accessibility review where the macro contains structured content, links, or images that may not render accessibly;
- a localization review for each language the macro will appear in.

Each approval MUST be recorded with the approver and the time. A macro MUST carry a version, an effective date, a review-by date, and an owner. A macro that has not been reviewed by its review-by date MUST be retired from the shared library or formally extended with a documented reason.

## Accuracy review

Each macro MUST be reviewed for factual accuracy against the current state of the product, the current policy, and the current legal environment. The review SHOULD be triggered automatically when a relevant change ships (a product change, a policy change, a regulator action, an incident with communications implications) rather than waiting for the next scheduled review. Macros that contain specific numbers, thresholds, dates, jurisdictions, or commitments MUST be reviewed with extra rigor, and SHOULD be flagged in the library so that an agent using them is reminded to confirm the values still apply.

## Expiration and retirement

Macros MUST carry an expiration date. A macro whose expiration has passed MUST be removed from the active library automatically, and any case using a recently expired macro SHOULD trigger a quality review. Macros for products, features, programs, or policies that have been retired MUST be archived rather than deleted so that audit can retrieve them when needed, but they MUST NOT be selectable by agents. The archive MUST be retention-bound consistent with the records-retention schedule.

## Language coverage

Macros SHOULD be available in every language the support function commits to. Each translation MUST be made by a qualified translator, MUST be reviewed by an editor fluent in that language, and MUST be reviewed for accessibility in that language (for example, screen-reader behavior, idiomatic clarity, avoidance of culturally inappropriate phrasing). Machine-translated macros MUST be post-edited by a human translator before publication. A macro that exists in one language but not another MUST NOT be auto-translated at the point of use unless the company has assessed that the auto-translation is safe for the content and the channel.

## Privacy and security

Macros MUST NOT contain hard-coded personal data, hard-coded credentials, hard-coded identifiers that allow account inference, or hard-coded links that include tokens. Macros MUST NOT instruct the customer to disclose information the company does not need. Macros MUST NOT contradict the privacy notices the customer has seen. Macros that reference a regulator, a complaint body, or a legal right MUST be reviewed by the legal function before publication and MUST be linked to the authoritative source so that the wording remains aligned.

## Use by AI-assisted agents

When an AI-assisted agent selects or composes a macro, the same approval and review rules apply. The selection SHOULD be logged so that audit can confirm the agent used a current macro rather than an expired or retired one. Macros that the AI-assisted agent is not authorized to send (for example, those that imply a refund, an account change, or a security commitment) MUST be filtered out before presentation. The agent MUST NOT silently edit an approved macro to add or remove content that would have changed the approval.

## Audit

The macro library SHOULD be audited for currency, completeness, accessibility, language coverage, and consistency with policy. Audit findings SHOULD feed the knowledge-governance and quality programs. Material findings MUST trigger a library refresh, a targeted retraining, or a revision of the approval workflow.

## Canonical sources

- ISO 18587:2017, Translation services — Post-editing of machine translation output — Requirements, https://www.iso.org/standard/62970.html
- W3C Recommendation, *Web Content Accessibility Guidelines (WCAG) 2.2*, https://www.w3.org/TR/WCAG22/
- ISO 9001:2015, Quality management systems — Requirements (clause 7.5 Documented information), https://www.iso.org/standard/62085.html
- Plain Language Action and Information Network (PLAIN), https://www.plainlanguage.gov/
