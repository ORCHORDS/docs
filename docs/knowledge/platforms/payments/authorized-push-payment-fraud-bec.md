# authorized-push-payment-fraud-bec

**Issue:** Defending against Authorized Push Payment (APP) fraud and Business Email Compromise (BEC) that trick users or staff into sending real payments to attackers
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
You get reports that a customer wired money to a "new" bank account after receiving an email that looked
like it came from your billing team. Or your own finance department paid an "updated" invoice after a
seemingly internal email asked them to change the vendor's routing details. The money is gone and the
real recipient never got paid.

This is APP fraud — the victim authorizes the payment themselves, so there is no card network chargeback
path and no automatic reversal. Per the 2026 AFP Payments Fraud Survey, 76% of organizations experienced
attempted or actual payments fraud in the prior year, and BEC/APP remains the single most common and
effective attack vector. Real-time payment rails (FedNow, RTP, SEPA Instant, UPI) make it worse because
settlement is near-instant, shrinking the window to recall funds.

Two flavors hit software businesses:

- **Inbound (your customers are the target).** Attackers spoof or compromise your domain, email customers
  that "our bank details have changed," and intercept the payment.
- **Outbound (your finance team is the target).** Attackers compromise a vendor's or executive's mailbox,
  then send your AP team a plausible invoice or change-of-banking-details request.

## Pattern / Solution
Treat banking-detail changes as the highest-risk transaction in your system. Layer the controls:

1. **Out-of-band verification for any bank-detail change.** When a customer or vendor reports changed
   banking details, require confirmation through a second, pre-established channel — a phone call to a
   number on file (not the number in the email), or a signed instruction through a separate portal. Never
   accept a banking change via email alone, even if the email looks internal.
2. **Server-side payee lock with grace period.** In your invoicing/billing system, store the last-known-good
   bank details. On any change request, queue the new details and hold payments to the new account for a
   window (e.g., 3 business days) while you verify. Display a prominent "banking details pending verification"
   flag in the UI.
3. **Email authentication hardening.** Enforce SPF, DKIM, and DMARC at `p=reject` on your own domain so
  attackers can't spoof you toward your customers. Monitor DMARC reports for unauthorized senders. This
  protects inbound (customers being defrauded in your name) and is evidence of due diligence.
4. **Payments Confirmation service where available.** In the UK, Confirmation of Payee (CoP) checks that
   the account name matches the account number before sending. Similar name-check services exist for
   FedNow/RTP in the US. Enable them at your bank and surface the result to the person approving the payment.
5. **Staff dual-control on outgoing wires.** Any payment above a threshold (e.g., $5,000) requires a
   second approver who did not initiate it, plus a verbal confirmation of the payee. Write this into the
   finance runbook, not just the security policy.
6. **Customer-facing warnings.** On every invoice, payment portal, and receipt, print: "We will never
   email you to change our bank details. Call [number] to verify any banking change." Reduces inbound
   spoofing success dramatically.

## Gotchas
- **APP fraud is not a chargeback.** Card networks give you 120 days to dispute; ACH/wire/real-time rails
  generally do not. Once the funds settle, recovery depends on the receiving bank's willingness to
  cooperate, which is slow and often fails. Plan for loss, not reversal.
- **Compromised vendor mailboxes are the most believable BEC.** The email genuinely comes from the
  vendor's real account, so SPF/DKIM/DMARC pass. This is why out-of-band verification is mandatory even
  when the email "checks out" cryptographically.
- **Reply-chain hijacking.** Attackers infiltrate a mailbox, watch an ongoing thread, and reply to it
  with new banking details at the natural moment. Train staff that a banking change mid-conversation is
  the classic tell, not a coincidence.
- **Real-time rails eliminate the recall window.** FedNow and RTP settle in seconds. The 3-day grace
  period in step 2 only works if you batch/defer; if a user can self-serve an instant payout to a
  just-added account, the grace period must be enforced in software, not in policy.
- **First-party fraud is rising alongside APP.** Per LexisNexis, first-party fraud (a "customer" who
  intends to dispute or reverse) doubled year over year. APP defense focuses on the sender being tricked;
  first-party defense is about the sender being the attacker. Different signals, different controls.
- **Don't put the verification phone number in the suspicious email.** Obvious but common — staff call
  the number in the fraudulent email to "verify" it. Use numbers from your CRM/records of prior contact.
- **Log the verification step.** If a payment is later disputed as fraud, your regulator or bank will
  ask what controls fired. Store who verified, through which channel, at what timestamp.

## Related
payment-audit-logging, fraud-detection-signals, velocity-fraud-checks, payment-error-handling,
real-time-payments-fraud-window
