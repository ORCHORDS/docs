# gdpr-data-breach-notification

**Issue:** GDPR Art. 33-34 — 72-hour breach notification to DPA and data subjects
**Date:** 2026-08-11
**Status:** documented

## Symptom
example.com discovers that a database containing
user email addresses and hashed passwords was
accessed by an unauthorised party. Someone asks
"do we need to notify the ICO/DPA?" You're not
sure what the threshold is or what 72 hours
actually means. The fine for failing to notify
is up to €10M or 2% of global turnover.

## Root cause
**GDPR Articles 33 and 34 impose mandatory breach
notification.** Art. 33 covers DPA notification
(72-hour rule). Art. 34 covers data subject
notification (without undue delay, where required).
UK GDPR mirrors these obligations post-Brexit.

**Source:**
- GDPR Art. 33-34: https://gdpr.eu/article-33/
- EDPB Guidelines 01/2021 on breach notification:
  https://edpb.europa.eu/our-work-tools/our-documents/guidelines/guidelines-012021-examples-regarding-personal-data-breach_en

## The "what counts as a breach" pattern (Art. 4(12))

For definition of a personal data breach:
"a breach of security leading to the accidental or
unlawful destruction, loss, alteration, unauthorised
disclosure of, or access to, personal data"

This includes:
- **Confidentiality breach:** Unauthorised access or
  disclosure (hacker exfiltrates data, wrong email)
- **Integrity breach:** Data altered by unauthorised party
- **Availability breach:** Data encrypted by ransomware,
  accidental deletion without backup

**Not a breach:**
- Encrypted device lost where keys are uncompromised
  (EDPB Guidelines 01/2021, Example 2)
- Emails sent to wrong recipient if immediately
  returned unread (minor, no risk)

**example.com specific risks:**
- S3 bucket misconfiguration exposing user content
- Database credential leak
- Third-party data processor breach (Stripe, email provider)
- Insider access to subscriber data
- Cloudflare Access misconfiguration exposing admin panel

## The "72-hour clock" pattern (Art. 33(1))

For the 72-hour countdown:
- **Starts:** When the controller "becomes aware" of
  the breach — not when it occurred, but when you
  have reasonable certainty a breach has taken place
- **Stops:** When you notify the supervisory authority
- **Without undue delay:** Notify as soon as possible;
  if not within 72 hours, explain the delay
- **Phased notification (Art. 33(4)):** Acceptable to
  notify with available information and supplement
  later — but initial notification must occur within 72h

**72 hours = 3 calendar days including weekends.**
Most DPAs accept notifications outside business hours
via online portal.

## The "DPA notification content" pattern (Art. 33(3))

For mandatory DPA notification contents:
1. **Nature of breach:** What type (confidentiality/
   integrity/availability), categories of data, approximate
   number of data subjects, approximate number of records
2. **DPO contact:** Name and contact details of Data
   Protection Officer (or other contact point)
3. **Likely consequences:** What harm could result
   (fraud, identity theft, reputational damage, etc.)
4. **Measures taken or proposed:** Remediation steps,
   containment measures, notification to data subjects

If all information is not available within 72 hours,
provide what is known and specify what is pending.

## The "DPA notification template" pattern

For example.com DPA notification (Art. 33) — minimum content:

---
**To:** [Relevant DPA — see below for jurisdiction]
**Subject:** Personal Data Breach Notification under GDPR Art. 33

**Controller:** [example.com entity name, address]
**DPO/Contact:** [Name, email, phone]
**Date/Time Breach Discovered:** [ISO 8601]
**Date/Time of This Notification:** [ISO 8601]
**Notification within 72 hours:** [Yes/No — if No, explain]

**Nature of Breach:**
Type: [Confidentiality / Integrity / Availability]
Categories of personal data: [e.g. email addresses,
hashed passwords, display names, subscription status,
content preferences, IP addresses]
Approximate number of data subjects: [X]
Approximate number of records: [X]

**Likely Consequences:**
[e.g. Risk of phishing attacks using exposed emails;
low risk of account takeover due to hashed passwords;
potential exposure of subscriber status for adult
content platform which could cause reputational harm]

**Measures Taken/Proposed:**
- [Containment: closed vulnerability at HH:MM on DATE]
- [Investigation: forensic review in progress]
- [Data subject notification: planned / not required because ...]
- [Password reset: forced for affected accounts]

**Further information to follow:** [Yes/No]
---

## The "data subject notification" pattern (Art. 34)

For when to notify data subjects:
- **Required when:** The breach is likely to result in
  **high risk** to the rights and freedoms of natural persons
- **Not required when:**
  - Data was encrypted with state-of-the-art key management
    (Art. 34(3)(a))
  - Subsequent measures eliminated the high risk (Art. 34(3)(b))
  - Notification to each subject would involve disproportionate
    effort → public communication instead (Art. 34(3)(c))

**High risk indicators for example.com:**
- Exposure of adult content subscription data → high
  risk of social harm, blackmail, discrimination
- Combination of email + password hash + content
  preferences → high risk even with hashing
- Financial data (payment method type, last 4 digits)
  → high risk

**Data subject notification content (Art. 34(2)):**
- Plain language description of the breach
- DPO contact details
- Likely consequences
- Measures taken to address/mitigate the breach
- Do NOT include information that would help attackers

## The "risk assessment" pattern (EDPB Guidelines)

For breach severity assessment:
- **Negligible risk:** No notification to DPA or
  data subjects required — document internally only
- **Low/medium risk:** Notify DPA (Art. 33). No
  data subject notification required.
- **High risk:** Notify DPA (Art. 33) AND data
  subjects (Art. 34). Without undue delay.

Factors (EDPB Guidelines 01/2021, Section III.C):
- Type of breach (confidentiality worst for social platforms)
- Nature of data (special category → higher risk)
- Number of affected persons
- Ease of identification of data subjects
- Severity of consequences
- Special characteristics of data subjects (vulnerable users)
- Special characteristics of controller (adult platform
  → subscriber data especially sensitive)

## The "UK GDPR parallel" pattern

For UK GDPR post-Brexit:
- **UK GDPR** (retained in UK law by European Union
  (Withdrawal) Act 2018, amended by Data Protection Act 2018)
  mirrors EU GDPR Art. 33-34 exactly
- **Supervisory authority:** ICO (Information Commissioner's
  Office), not an EU DPA
- **72-hour rule:** Same — 72 hours to notify ICO
- **ICO notification portal:**
  https://ico.org.uk/for-organisations/report-a-breach/
- **Parallel notifications:** If example.com has EU users
  (GDPR) AND UK users (UK GDPR), you may need to notify
  both the lead EU DPA and the ICO in parallel
- **Lead EU DPA jurisdiction:** Determined by main
  establishment in EU. If no EU establishment, notify
  DPA in each member state where data subjects are affected

## The "record-keeping" pattern (Art. 33(5))

For internal breach register:
- **Mandatory regardless of whether DPA notification
  is required** (Art. 33(5))
- Document: facts of breach, effects, remedial actions
- Retain: indefinitely (to demonstrate compliance to DPA)
- Review: annually with DPO

## What example.com must do

1. **Incident response plan:** Build a documented breach
   response procedure with: detection → containment →
   assessment → 72h DPA decision → data subject decision.
   Test it annually.
2. **DPA identification:** Identify lead supervisory
   authority (main EU establishment or, if none, each
   member state DPA). Identify ICO for UK users.
   Bookmark both notification portals.
3. **DPO appointment:** Assess if DPO is mandatory
   (Art. 37 — large-scale processing of special category
   data; adult content platform processing user content
   preferences likely qualifies). If in doubt, appoint one.
4. **Breach register:** Implement breach register now.
   Every breach, however minor, must be documented.
5. **High-risk assessment:** For adult content platform,
   treat exposure of subscription/content preference data
   as HIGH risk by default → mandatory data subject
   notification. Prepare a notification template.
6. **72-hour logistics:** Ensure someone can initiate
   DPA notification at any time (including weekends).
   DPA portals are online; no business hours restriction.
7. **Encryption:** Encrypt data at rest with AES-256.
   If an encrypted database is lost/stolen, this may
   eliminate the notification requirement (Art. 34(3)(a))
   — document your key management as part of the assessment.
8. **Processor breaches:** If Stripe, an email provider,
   or Cloudflare suffers a breach affecting example.com
   data, they must notify you "without undue delay" (Art.
   33(2)). Your 72-hour clock starts when they notify you.
   Ensure processor contracts include Art. 28(3)(f) obligations.
