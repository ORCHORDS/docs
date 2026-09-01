# PCI DSS Marketing Payment Page Controls

## Scope

This control applies when marketing pages, landing pages, donation pages, event-registration pages, subscription pages, campaign microsites, tag managers, analytics pixels, A/B testing tools, personalization scripts, chat widgets, affiliate scripts, or consent-management tools are present on a page that collects or can affect payment-card data. It also applies when marketing owns a page that redirects to a hosted payment page or embeds payment fields from a payment service provider.

The goal is to prevent marketing technology from weakening payment-page security, expanding cardholder-data scope, or interfering with payment integrity. This document does not certify PCI DSS compliance and does not interpret payment-brand rules for any specific merchant. The canonical primary sources for this control are the PCI Security Standards Council’s [PCI DSS document library](https://www.pcisecuritystandards.org/document_library/) and the Council’s [PCI DSS v4.0 resource hub](https://www.pcisecuritystandards.org/standards/pci-dss/).

## Requirements Versus Recommendations

Required controls:

- Maintain an inventory of all scripts, iframes, tags, pixels, and third-party code that execute on payment pages or pages that can influence payment submission.
- Document the business justification for each script and approve it before deployment.
- Verify that payment-page scripts have not changed without authorization.
- Prevent marketing tools from collecting primary account number, card verification code, expiration date, authentication data, or payment tokens unless the tool is explicitly approved for that data class.
- Restrict who can modify tags or page templates affecting payment pages.
- Retain validation evidence for page integrity, script inventory, access review, and change approval.

Recommended controls:

- Keep marketing and payment experiences separated so that promotional scripts do not execute in the payment frame or on the hosted payment page.
- Prefer hosted payment fields or hosted payment pages from a validated provider.
- Use Content Security Policy, Subresource Integrity where suitable, iframe isolation, and tag-manager environment separation.
- Disable session replay, heatmaps, and full DOM capture on payment pages unless security and privacy review approves a masked configuration.

## PCI DSS Context

PCI DSS v4.0 and later versions include specific attention to ecommerce payment-page scripts and page integrity. Teams must verify the applicable version, service-provider responsibilities, and required implementation dates for their environment. PCI SSC publishes official standards and supporting guidance through its document library; the organization’s Qualified Security Assessor or internal security assessor should determine which requirements apply.

Marketing is often not the system owner for cardholder data, but marketing choices can materially affect the payment page. A tag added for attribution can load additional third-party code. A session replay tool can capture sensitive fields if masking fails. A test variation can move disclosures or buttons in ways that alter checkout behavior. A compromised script can skim card data even if the payment form is otherwise secure. For these reasons, marketing-controlled technology must be governed as part of payment-page security.

## Workflow

Any page that accepts payment details, hosts payment fields, redirects to payment collection, or sits immediately before payment submission must be classified before tags are added. The page owner completes a payment-page marketing intake. The intake identifies page URL patterns, payment provider, form type, cardholder-data exposure, tag manager container, analytics tools, testing tools, personalization tools, consent tools, chat tools, and deployment pipeline.

Security reviews the intake and assigns the page to a control tier. Tier 1 includes pages where cardholder data can be entered directly into merchant-controlled DOM. Tier 2 includes merchant pages with embedded hosted payment fields. Tier 3 includes marketing pages that redirect to a fully hosted provider page. Tier 1 and Tier 2 require stricter controls; Tier 3 still requires redirect integrity and avoidance of deceptive pre-payment handling.

Before launch, every script must have an owner, purpose, source URL, vendor, data collected, destination domain, approval ticket, and monitoring rule. The tag manager must use separate containers or environments for payment pages when possible. Publishing rights must be limited to trained users. Emergency tag changes must be logged and reviewed after deployment.

After launch, automated monitoring checks the page for script additions, domain changes, hash changes where used, broken CSP reports, unauthorized tag-manager versions, and unexpected network calls. Any unauthorized change triggers incident triage.

## Concrete Fields And Controls

Script inventory fields:

- `page_group`: checkout, donation, subscription, event, redirect, or confirmation.
- `url_pattern`: controlled URL or route.
- `script_id`: stable script or tag identifier.
- `script_source`: first-party, payment provider, analytics, ads, experimentation, chat, consent, fraud, or other.
- `vendor_name`: legal vendor name.
- `source_url`: canonical script URL or tag template.
- `business_purpose`: documented justification.
- `data_access`: none, page metadata, user identifiers, transaction metadata, payment field proximity, or sensitive.
- `approved_by_security`: reviewer and date.
- `approved_by_marketing`: owner and date.
- `change_ticket`: deployment approval.
- `integrity_control`: CSP, SRI, hash monitor, file integrity monitor, provider attestation, or compensating control.
- `last_verified`: timestamp of most recent scan.

Technical controls must include restricted tag-manager permissions, production publish approval, version rollback, payment-page container separation, CSP allowlists, script-change detection, network-call monitoring, and masking rules for analytics or replay. Payment fields must not be named or labeled in ways that cause non-payment scripts to scrape them. Marketing forms must not ask for card data outside the approved payment component.

## Validation Evidence And Tests

Validation evidence includes current script inventory, screenshots of page classification, tag-manager permission export, approval tickets, CSP configuration, scan output, network-call capture, payment-provider integration diagram, and a sample transaction showing that card data flows only to the approved provider.

Tests must include:

- Script inventory test: crawl payment-page URLs and compare discovered scripts with the approved inventory.
- Unauthorized script test: attempt to publish a new tag to a payment-page environment and verify approval blocks it.
- Sensitive capture test: confirm analytics, pixels, replay, and logging tools do not receive card number, security code, or full payment tokens.
- CSP test: verify unapproved domains are blocked or reported according to policy.
- Change-detection test: modify a controlled script in a test environment and verify alert generation.
- Rollback test: publish and revert a tag-manager version in staging.
- Evidence replay test: reconstruct which scripts ran on a sampled transaction date.

Primary-source references for the evidence package should include the PCI SSC [document library](https://www.pcisecuritystandards.org/document_library/) and the PCI SSC [PCI DSS standard overview](https://www.pcisecuritystandards.org/standards/pci-dss/). If an assessor relies on a specific PCI DSS PDF or FAQ, attach that source by title and publication date rather than paraphrasing from memory.

## Failures And Corrections

Common failures include allowing broad marketer publish rights in production tag managers, adding retargeting pixels to checkout without review, enabling session replay without field masking, failing to inventory scripts loaded by other scripts, assuming a hosted payment iframe eliminates all page-security responsibility, or keeping obsolete tags after a campaign ends.

Corrections depend on severity. If an unauthorized script was present on a payment page, remove or disable it, preserve forensic evidence, identify when it was active, and determine whether it accessed sensitive data. If sensitive data may have leaked to a marketing vendor, escalate to security, privacy, legal, and payment-compliance owners. If the issue is governance rather than compromise, update approvals, permissions, and monitoring so the same path cannot recur.

For repeated tag-manager failures, remove direct production publish rights from marketing users and require deployment through the engineering release process. For vendors that cannot document data collection, disable them on payment pages until review is complete. For scripts with unclear purpose, remove them by default; attribution convenience is not a sufficient reason to preserve payment-page risk.

## Limitations

This control is not a substitute for a complete PCI DSS assessment, penetration test, segmentation review, or service-provider responsibility matrix. It does not determine whether the merchant qualifies for a particular Self-Assessment Questionnaire. It also does not prove that a payment provider is compliant. It addresses the marketing-controlled portion of payment-page risk and the evidence that marketing must provide to security and payment-compliance teams.

No document owner may state that a payment page is “PCI compliant” because these controls passed. The approved statement is narrower: marketing-controlled scripts and tools on the identified payment-page routes were inventoried, approved, monitored, and tested under this control as of the evidence date.

## Canonical sources

- **Primary authority 1 — PCI DSS document library:** [https://www.pcisecuritystandards.org/document_library/](https://www.pcisecuritystandards.org/document_library/)
- **Primary authority 2 — PCI DSS v4.0 resource hub:** [https://www.pcisecuritystandards.org/standards/pci-dss/](https://www.pcisecuritystandards.org/standards/pci-dss/)
