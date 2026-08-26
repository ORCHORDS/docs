# UK DMCC subscription-contract readiness controls

**Issue:** The Digital Markets, Competition and Consumers Act 2024 contains a new UK subscription-contract regime covering pre-contract information, reminders, ending contracts, and cooling-off rights. As of 2026-08-18, the government anticipates commencement in spring 2027 and further regulations and guidance are still material, so production logic must be prepared without falsely treating draft timing or detail as in force.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** readiness — not yet commenced

## Applicability and controls

- Inventory UK consumer contracts with auto-renewal, indefinite continuation, free trials, introductory pricing, or a consumer action required to avoid ongoing or higher charges.
- Map excluded contract categories and existing Consumer Contracts Regulations duties separately; do not infer scope from the word “subscription” alone.
- Store versioned key and full pre-contract information, the consumer’s affirmative action, contract time, price, renewal cadence, minimum commitment, trial or concession end, and supplied durable-medium record.
- Build configurable reminder notices whose content, prominence, channel, and timing can follow final regulations.
- Provide a straightforward, accessible cancellation path and durable end-of-contract acknowledgment; do not add retention friction.
- Model initial and renewal cooling-off events, notices, cancellation instructions, refunds, and any lawful payment for service supplied as configurable rules.
- Preserve an evidence timeline for notice generation, delivery outcome, cancellation, refund, and customer support.
- Feature-flag the new regime by contract date and jurisdiction only after legal approval.

## Implementation and tests

Create a contract-state machine for signup, trial, recurring period, long renewal, reminder windows, cancellation, cooling-off, refund, failed delivery, and termination. Test mobile, desktop, telephone-assisted, accessibility, offline support, bounced messages, changed contact details, price changes, immediate cancellation, and cancellation during each cooling-off window.

Before activation, compare final commencement regulations and government guidance with every rule and rerun journey, notice, and refund tests.

## Gotchas and legal caveat

The Act has been enacted, but these subscription provisions require commencement. The April 2026 government response anticipates spring 2027; that is not itself the legal commencement instrument. Secondary regulations can settle or change operational details. Verify the current legislation, commencement order, exclusions, regulations, and guidance on the activation date.

Existing consumer-protection law continues to matter. This readiness note is not legal advice.

## Official sources

- [UK legislation: DMCC Act 2024 explanatory notes, subscription contracts](https://www.legislation.gov.uk/ukpga/2024/13/notes/division/9/index.htm)
- [UK government response on implementation of the subscription-contract regime](https://www.gov.uk/government/consultations/consultation-on-the-implementation-of-the-new-subscription-contracts-regime/outcome/government-response-to-consultation-on-the-implementation-of-the-new-subscription-contracts-regime-web-accessible-version)
- [UK legislation: DMCC Act commencement](https://www.legislation.gov.uk/ukpga/2024/13/notes/division/11/index.htm)
