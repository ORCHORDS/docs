# pci-dss-v4-client-side-script-integrity

**Issue:** Meeting PCI DSS v4.0 requirements 6.4.3 and 11.6.1 for payment page script integrity and tamper monitoring (Magecart defense)
**Date:** 2026-08-13
**Status:** documented

## Symptom / Context
An assessor flags your checkout page for non-compliance, or a QSA rejects your SAQ A because you load
third-party scripts (analytics, chat widgets, A/B testing, tag managers) on the payment page. PCI DSS v4.0
introduced future-dated requirements that became effective 31 March 2025 and are now enforced in 2026.
The two that catch teams off guard:

- **Req 6.4.3** — All payment-page scripts must have their integrity verified (hash/SRI), their authorization
  documented, and their purpose justified. This applies to every script the browser loads on a page that
  renders card fields, even via iframe.
- **Req 11.6.1** — You must deploy a change- or tamper-detection mechanism on payment pages that alerts on
  unauthorized modification. Manual review is no longer sufficient.

The classic failure: you use Stripe Payment Elements (iframe, SAQ A eligible) but you also load Google
Analytics, Hotjar, a Facebook Pixel, and a chat widget on the same page. Each is a Magecart vector. A
compromised vendor CDN script can skim card data even though your iframe is "secure."

## Pattern / Solution
Build and maintain a **payment-page script inventory** before anything else. For every script loaded on
the checkout URL:

1. **Inventory and justify.** Record script URL, vendor, purpose, owner, and the business reason it must
   appear on the payment page specifically (not the rest of the site). If it doesn't need to be on
   checkout, remove it. Most scripts belong on landing/product pages, not checkout.
2. **Add Subresource Integrity (SRI) hashes.** For scripts you control, add `integrity="sha384-..."`
   attributes. For vendor scripts, request pinned versions with SRI from the vendor. If a vendor won't
   provide SRI-compatible pinned versions, that's a red flag — treat it as scope risk.
3. **Lock the Content Security Policy.** Ship a CSP with a tight `script-src` allowlist (no `unsafe-inline`,
   no wildcards). This both satisfies the "authorization" part of 6.4.3 and makes tampering fail closed.
4. **Deploy tamper detection (Req 11.6.1).** Run an automated monitor that fetches the live payment page
   on a schedule, hashes the rendered DOM and loaded script list, and alerts on any drift. Tools range
   from commercial (Feroot, Source Defense, Subresource Integrity monitors) to a scripted headless-browser
   check that diffs the script manifest against a baseline. Alerts must go to a human, not just a log.
5. **Document the review cadence.** PCI v4 wants evidence of ongoing review, not a one-time snapshot.
   Log every change to the script inventory with date, approver, and risk note.

## Gotchas
- **Tag managers are the biggest hole.** Google Tag Manager, Segment, and Tealium can inject arbitrary
  scripts at runtime, defeating static SRI. You either exclude GTM from the payment page entirely, or
  use a container-locking feature that prevents runtime script injection. Many QSAs treat a tag manager
  on checkout as an automatic SAQ A → SAQ A-SP or SAQ D escalation.
- **SRI breaks vendor updates.** When a vendor ships a new script version, your SRI hash mismatch blocks
  it — which is the point, but it also breaks checkout. Pin versions explicitly and update hashes through
  a deliberate release, never auto-updating CDN "latest" tags.
- **Req 11.6.1 is not "we have a WAF."** A WAF inspects inbound requests; it does not detect that the
  checkout page is now loading `skimmer.js` from a lookalike domain. You need client-side / DOM-level
  monitoring, which is a different tool category.
- **Webhooks and backend scripts are out of scope here.** 6.4.3 is specifically about scripts executed
  in the cardholder's browser on the payment page. Don't conflate it with server-side dependency scanning
  (that's Req 6.3, covered elsewhere).
- **"We use Stripe so we're fine" is wrong.** Stripe Elements keeps card data out of your server scope,
  but third-party scripts you load alongside it can still read the DOM and exfiltrate. SAQ A eligibility
  can be voided by a single rogue analytics script.
- **Screenshot your monitor.** For audit evidence, retain dated outputs of the tamper-detection baseline
  and any alert resolutions. Assessors ask for proof the mechanism ran, not just that it exists.

## Related
pci-dss-saq-a-compliance, pci-dss-scope-reduction, tokenization-vault-patterns, fraud-detection-signals,
card-testing-attack-prevention
