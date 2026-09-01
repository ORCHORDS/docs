# Marketing One-Time Offer Clock Enforcement

A countdown timer is a factual assertion. When a storefront tells a shopper that an offer ends at midnight, or that a discount is available "once," the shopper is entitled to rely on that statement in the same way as on the price itself. This article governs the engineering and evidence discipline that makes limited-time and one-time offers genuine: the offer clock must actually expire, the expiry must be enforced server-side, and the organization must be able to show that the clock was not reset to manufacture urgency. A timer that restarts on every page load is not a timer; it is a false statement rendered in JavaScript.

## Scope

This control covers every time-limited or frequency-limited offer presented in marketing-owned experiences: countdown timers on landing pages, cart-level expiry claims, first-purchase discounts, "offer ends today" banners, limited-availability promotional pricing, one-time redemption codes, and win-back offers presented once per customer. It applies to the offer definition, the clock implementation, the redemption enforcement path, and the audit evidence tying each rendered timer to a real expiry.

It does not cover general pricing-claim substantiation or comparative price evidence, which are governed separately, and it does not evaluate whether the underlying discount is economically honest. Its single question is narrower: did the constraint the customer was shown actually bind?

## Workflow or implementation guidance

1. **Define the offer as data, not copy.** Each timed offer is created as a record with a stable identifier, start time, end time, timezone, eligible audience, redemption limit, and per-customer limit. The rendered timer reads this record; the redemption path reads the same record. Copy that mentions time limits without a backing record is rejected at review.
2. **Compute the deadline server-side.** The client receives the deadline as an absolute UTC timestamp plus the display timezone, and renders a countdown from the customer's local clock. The client never supplies the deadline, only displays it, so tampering with the browser clock changes the display but not eligibility.
3. **Enforce at redemption, not at render.** Redemption attempts are evaluated against the offer record at the moment of application: an expired offer returns a clear message rather than silently applying. A countdown that reaches zero and then still applies the discount is a defect even when it pleases the customer, because the displayed constraint was false.
4. **Bind the timer to the session honestly.** Timers that reset on refresh, on device change, or on incognito visit communicate a false premise unless the offer record itself defines a rolling window. Where a rolling per-visitor window is genuinely intended, the mechanism is documented in the offer record and the rendered language is checked so it does not imply a fixed calendar deadline.
5. **Record offer-state transitions.** The offer service writes an append-only log: creation, schedule changes, activation, expiry, and early termination. Any change to an end time after activation is an exceptional event requiring approval, and the log preserves both the old and new value.
6. **Never extend invisibly.** If an offer is extended for operational reasons, the extension is recorded with rationale, and customers who saw the original deadline are not the target of a second urgency message based on the same offer. Repeated extensions of a "final" offer convert it into a standing price and are escalated to pricing review.
7. **Test expiry as a first-class path.** Every launch test suite includes a time-travel or clock-override test that advances past the end time and verifies both display and redemption behavior.

## Controls

- Offer records are immutable after activation except through the approved change path, which requires a second approver and writes both values to the log.
- A scheduled verification job loads each active offer page, extracts the rendered deadline, and compares it to the offer record; mismatches alert immediately.
- Redemption services independently query the offer record rather than trusting parameters supplied by the client.
- Per-customer limits are enforced against a durable redemption ledger keyed by customer and offer, not by cookie or local storage.
- The copy review gate blocks time-limited language on offers without a backing end time, and blocks "one time" language on offers without a per-customer limit.
- Countdown components display the timezone basis where the deadline could plausibly be read as local time.

## Validation evidence

- The offer record for each flighted offer: identifier, start, end, timezone, limits, and the full append-only change log.
- Rendered-page captures showing the timer value alongside the offer record at capture time, taken by the verification job across the flight window.
- Time-travel test results demonstrating post-expiry display and redemption rejection, plus a same-offer re-visit test confirming the timer does not reset for a fixed-deadline offer.
- Redemption ledger extracts showing per-customer limits holding across multiple attempts, including attempts from different sessions and devices.
- Change-log extracts for every post-activation modification, with approver and rationale.

## Failure modes and correction

Frequent failures include a timer reset per session because the deadline was generated at impression time, a countdown that reaches zero and still honors the code, a per-customer limit enforced only by cookie so a second device redeems twice, an end time stored without timezone so the offer dies at the wrong hour, and a marketing team repeatedly cloning and extending an expired "one-time" offer under new identifiers to re-run urgency against the same audience. The cloned-extended pattern is the most serious because it is deliberate: the same population receives the same "final" scarcity message repeatedly.

Correction starts with disabling the deceptive mechanism, not with deleting the evidence. The offer log, rendered captures, and redemption records are preserved. Customers who redeemed under a falsely extended constraint are evaluated for remediation; customers who saw a false deadline and did not purchase require a decision on whether corrective communication is warranted, which is escalated rather than decided by the campaign owner. The timer implementation defect is fixed and the time-travel suite is extended to cover the specific failure. Deliberate extension patterns are escalated to governance and may trigger withdrawal of the campaign team's authority to create timed offers without review.

## Limitations

This control governs enforcement and evidence, not the persuasiveness or legality of urgency marketing generally; genuinely expiring offers can still be questioned on other grounds such as reference-price honesty. Server clocks, timezone databases, and downstream caching each introduce small windows where display and eligibility can disagree; the control requires detection rather than impossibility. Scarcity claims based on inventory rather than time are covered by separate availability controls. Nothing here approves a pattern in which technically enforced clocks are paired with misleading copy about what will happen at expiry.

## Canonical sources

- **Primary authority 1 — Federal Trade Commission, Advertising FAQs: A Guide for Small Business (deceptive pricing and false urgency claims):** [https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business](https://www.ftc.gov/business-guidance/resources/advertising-faqs-guide-small-business)
- **Primary authority 2 — Federal Trade Commission, Guides Against Deceptive Pricing, 16 CFR Part 233:** [https://www.ftc.gov/legal-library/browse/rules/guides-against-deceptive-pricing](https://www.ftc.gov/legal-library/browse/rules/guides-against-deceptive-pricing)
- **Reference — RFC 3339, Date and Time on the Internet: Timestamps:** [https://www.rfc-editor.org/rfc/rfc3339](https://www.rfc-editor.org/rfc/rfc3339)
