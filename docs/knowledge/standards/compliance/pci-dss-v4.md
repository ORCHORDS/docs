# pci-dss-v4

**Issue:** PCI DSS v4.0 — example.com scope with Stripe and Cloudflare
**Date:** 2026-08-11
**Status:** documented

## Symptom
example.com uses Stripe for subscriptions and
Stripe Connect for creator payouts. You want to
know your actual PCI DSS scope. Someone says
"Stripe handles it." But a QSA tells you the
scope depends on your integration type. The
fine for non-compliance is card scheme termination.

## Root cause
**PCI DSS v4.0 is mandatory since March 2024**
(v3.2.1 retired 31 March 2024). v4.0.1 issued
June 2024. SAQ type determines scope. Stripe
and Cloudflare both affect scope — but they do
not eliminate your obligation entirely.

**Source:** PCI SSC:
https://www.pcisecuritystandards.org/

## The "Stripe scope reduction" pattern

For Stripe integration types and PCI impact:
- **Stripe.js + Stripe Elements (hosted fields):**
  Card data entered directly in Stripe's iframe.
  Your servers never see PANs.
  → **SAQ A** (22 requirements, simplest)
- **Stripe Checkout (hosted page):**
  Cardholder redirected to Stripe's domain entirely.
  → **SAQ A**
- **Stripe Mobile SDK (iOS/Android):**
  SDK tokenises before reaching your app.
  → **SAQ A** (mobile)
- **Direct API with card data sent to your server:**
  Your server passes raw PANs to Stripe.
  → **SAQ D** (full 12 requirements) — avoid this

**example.com recommendation:** Use Stripe Elements
or Stripe Checkout. This achieves SAQ A and
dramatically reduces scope.

## The "SAQ types" pattern

For Self-Assessment Questionnaire types:
- **SAQ A:** E-commerce, card-not-present, all
  processing outsourced to PCI-compliant third party.
  22 requirements. Annual SAQ + quarterly ASV scan.
- **SAQ A-EP:** E-commerce that partially outsources
  but scripts could affect payment page.
  191 requirements. Use Stripe.js subresource
  integrity hashes to avoid this.
- **SAQ B:** Imprint machines or standalone terminals.
  Not applicable to online platform.
- **SAQ D:** All merchants not in A/A-EP/B/C/P2PE.
  Full 12 requirements. ~329 controls. Avoid.

**Key question:** Does any JavaScript on example.com
pages affect the payment form? If yes → SAQ A-EP.
Use Content Security Policy and Stripe's Subresource
Integrity (SRI) to stay at SAQ A.

## The "Cloudflare as Level 1 SP" pattern

Cloudflare is a **PCI DSS Level 1 Service Provider**
(validated annually by QSA). Cloudflare's services:
- DDoS protection
- WAF (Web Application Firewall)
- CDN / TLS termination
- Bot management

**What this means:**
- Cloudflare's Attestation of Compliance (AoC) can
  be used to demonstrate security controls at the
  edge layer
- Download Cloudflare's AoC from:
  https://www.cloudflare.com/trust-hub/compliance-resources/
- Include Cloudflare in your Service Provider List
  (Requirement 12.8.4 — annual review)
- Cloudflare TLS: Ensure "Full (Strict)" mode so
  the entire path is encrypted (Req 4.2.1)

## The "Stripe Connect" pattern

For creator payouts via Stripe Connect:
- **Standard accounts:** Creators onboard directly
  to Stripe. Stripe handles their KYC and card data.
  Your platform does not handle creator bank/card data.
  → No additional PCI scope from Connect Standard.
- **Custom/Express accounts:** If you collect creator
  payout details through your own UI and pass to
  Stripe → assess whether bank account numbers are
  in scope. Bank account numbers are not PANs and
  are outside PCI DSS scope but are within GDPR scope.
- **Marketplace payments:** If example.com holds funds
  in transit, assess money transmission licensing
  separately (FCA in UK, EMI licence in EU).

## The "network segmentation" pattern (Req 1.3)

For network segmentation to limit CDE:
- **CDE:** Systems that store, process, or transmit
  cardholder data. With SAQ A, your CDE is essentially
  empty — Stripe's iframe is the CDE.
- **Connected systems:** Systems that can communicate
  with the CDE are in scope even if not storing card
  data. Segment your payment-related services.
- **Penetration test:** Annual pen test must validate
  that segmentation is effective (Req 11.4.5)
- **Cloudflare WAF:** Include in network diagram as
  perimeter control

## The "customised approach" pattern (v4.0 new)

PCI DSS v4.0 introduced Customised Approach:
- Allows entities to demonstrate intent of requirement
  through alternative controls
- Requires documented Target Risk Analysis (TRA)
- Not available for SAQ merchants — only ROC-level
- For example.com at SAQ A: use defined approach,
  not customised approach

## The "annual requirements" pattern

For annual PCI DSS obligations at SAQ A:
- **SAQ A form:** Complete and sign annually
- **Quarterly ASV scans:** External vulnerability
  scans by Approved Scanning Vendor (Req 11.3.2)
  — even for SAQ A merchants
- **Service provider review:** Confirm Stripe and
  Cloudflare PCI compliance annually (Req 12.8.4)
- **Penetration test:** At least annually and after
  significant changes (Req 11.4.3) — scope is limited
  for SAQ A but good practice
- **Policy review:** Annual review of security policies

## What example.com must do

1. **Integration audit:** Confirm all payment flows
   use Stripe Elements or Stripe Checkout, not raw
   card data transmission. Document in a data flow
   diagram.
2. **SAQ A completion:** Complete SAQ A annually.
   Submit to acquiring bank. Keep signed copy.
3. **ASV scans:** Engage an ASV for quarterly external
   scans of internet-facing IPs. Remeditime any
   findings before submitting to acquirer.
4. **Service provider list:** Maintain a list of all
   service providers with PCI scope (Stripe, Cloudflare).
   Download their AoCs annually. Store in compliance
   folder.
5. **Content Security Policy:** Implement CSP header
   to prevent third-party JS injection on payment
   pages. Use Stripe's SRI hash. This keeps you at
   SAQ A rather than SAQ A-EP.
6. **Cloudflare:** Enable Full (Strict) SSL mode.
   Enable WAF with OWASP ruleset. Document Cloudflare
   as a Level 1 SP in your network diagram.
7. **Incident response:** If a payment card breach
   occurs, notify your acquiring bank immediately.
   Card schemes (Visa/Mastercard) have their own
   breach response programmes independent of GDPR.
