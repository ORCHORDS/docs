# User Privacy vs. Law Enforcement Requests

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Law enforcement sends a data demand for a user who posted
content under an anonymous session. The platform holds only
an IP address log, session token, and timestamp — no account.
A foreign police agency sends a second demand by email with
no US court order. A civil subpoena from a private plaintiff
seeks the poster's identity. Each demand has different legal
weight, a different disclosure standard, and a different
platform obligation. Treating them identically creates both
liability and constitutional risk.

## Context

example project is an anonymous 21+ platform. By design it collects
minimal data: no registration, no email, no account profile.
Data held includes IP address logs (30-day retention), hashed
session tokens, content metadata, and payment records held
separately by NOWPayments. The minimal data posture is both a
privacy design choice and a compliance defense: the platform
cannot disclose what it does not hold.

## Warrant vs. subpoena vs. court order

```
US legal process hierarchy (ECPA / SCA):

  Warrant (most demanding):
    Requires: judicial finding of probable cause
    Signed by: judge or magistrate
    Covers: content of stored communications
    (ECPA § 2703(a)/(b)(1)(A) — < 180 days or open)
    Platform must comply; may not notify user if gag applies

  § 2703(d) Court Order:
    Requires: specific articulable facts showing relevance
    (lower bar than probable cause)
    Signed by: judge
    Covers: non-content records — IP logs, metadata, session
    records, access timestamps

  Subpoena (least demanding):
    Requires: attorney / grand jury certification
    (no judicial review for basic subscriber info)
    Covers: basic subscriber info only (ECPA § 2703(c)):
    name, address, session times, connection records

  Civil subpoena for anonymous poster identity:
    Requires First Amendment "Doe subpoena" review before
    compliance. Court must find plaintiff has a prima facie
    valid claim (Dendrite / Cahill standard). Platform should
    notify user before disclosing to allow them to challenge.
```

## Data preservation vs. disclosure

```
18 U.S.C. § 2703(f) — Preservation request:

  On receipt from law enforcement:
  → Platform MUST preserve records for 90 days
  → Renewable once for additional 90 days
  → Preservation ≠ disclosure; data held pending legal process
  → Do NOT delete preserved data under normal retention schedule
  → Preservation request may arrive before legal process; hold
    data pending follow-up warrant, order, or subpoena

Data category → required legal process:

  IP address, session token, session timestamp:
    → Subpoena sufficient (§ 2703(c)(1)(C))
    → But courts are split: IP as the only identifier on an
      anonymous platform may require higher process

  Non-content transactional records (access logs):
    → § 2703(d) order required

  Content of stored communications (posts, messages):
    → Warrant required (§ 2703(a))
    → Post-Warshak, warrant is the safer standard for
      all stored content regardless of age
```

## Data minimization as a legal defense

```
GDPR Art. 5(1)(c): collect only necessary data.
ECPA: you can only disclose what you hold.

example project minimization posture:

  Collect: IP address (Cloudflare log), HMAC-hashed session
    token, content metadata (post timestamp, content hash)

  Do NOT collect: email, raw device fingerprint, account
    linkage across sessions, geolocation below country level

  Retention schedule:
    → IP logs: 30 days
    → § 2703(f) preservation request: extend to 90 days
    → Session tokens: 7 days after session expiry

  The minimization defense:
    "We hold: IP address log retained 30 days — now purged.
    We do not hold email, device ID, or account records."
    Document retention policy and enforcement in writing
    before any demand arrives.
```

## Foreign law enforcement requests

```
Email / informal demand:
  → Request formal MLAT process; do not comply informally

US court (letters rogatory / 28 U.S.C. § 1782):
  → Treat as US court order; comply per ECPA process

CLOUD Act agreement country (UK, EU, etc.):
  → Comply if order meets CLOUD Act (18 U.S.C. § 2523)
    standards and US constitutional minimums

GDPR conflict:
  → Disclosing EU-resident data to non-EU law enforcement
    without MLAT or adequacy decision may violate GDPR Art. 48
  → Formal MLAT channels are the legally safe path

Never comply without legal counsel; never allow direct
foreign agency access to platform systems.
```

## Anti-patterns

- **Complying with civil Doe subpoenas without First Amendment
  review** — courts require a prima facie showing of a valid
  claim before anonymous speech can be unmasked. Compliance
  without this review exposes users and invites § 2707 claims.
- **Retaining data indefinitely "in case law enforcement asks"**
  — this inverts the minimization principle, expands the
  disclosure surface, and conflicts with GDPR Art. 5(1)(e)
  storage limitation.
- **Treating all legal demands as equivalent** — a warrant, a
  § 2703(d) order, and a civil subpoena cover different data.
  Disclosing content in response to a subpoena is a violation.
- **Disclosing in response to informal foreign demands** —
  informal compliance with foreign agencies creates GDPR Art.
  48 exposure and sets a precedent outside formal MLAT channels.

## Gotchas

- **IP addresses rarely identify a person directly** — carrier-
  grade NAT maps many users to one IP. Law enforcement must
  subpoena the ISP separately for subscriber-to-IP mapping.
- **National Security Letters (NSLs)** — FBI can demand subscriber
  info without court order and prohibit disclosure of the NSL's
  existence. Route to legal counsel immediately on receipt.
- **Voluntary emergency disclosure (§ 2702)** — permissive for
  imminent risk of death or serious harm. Document: who
  requested, what was disclosed, date, and basis.
- **Gag orders** — if present, do not notify the user. If absent,
  notify the user 7-10 days before disclosing so they can
  move to quash.

## Verification

- IP log retention policy (30 days) is documented and enforced.
- Legal process review checklist distinguishes warrant /
  § 2703(d) order / subpoena before any data is released.
- Civil Doe subpoena procedure includes First Amendment review.
- § 2703(f) preservation requests extend retention to 90 days
  and are logged in the legal hold register.
- Transparency report published at least annually.
- Foreign requests are routed to legal counsel before disclosure.

## Related

- `documentation/categories/issues/anonymous-platform-abuse-prevention.md`
- `documentation/categories/issues/platform-liability-section-230-dsa.md`
- `documentation/categories/compliance/privacy-enhancing-technologies-pets.md`
- `documentation/categories/security/audit-logging.md`

## Source URLs (verified 2026-08-17)

- ECPA Stored Communications Act (18 U.S.C. §§ 2701-2712)
  — https://www.law.cornell.edu/uscode/text/18/part-I/chapter-121
- DOJ CCIPS — Searching and Seizing Computers manual
  — https://www.justice.gov/criminal/file/442111/download
- CLOUD Act (18 U.S.C. § 2523) full text
  — https://www.law.cornell.edu/uscode/text/18/2523
- EFF — Who Has Your Back transparency guide
  — https://www.eff.org/who-has-your-back
- Dendrite Int'l v. Doe — anonymous speaker subpoena standard
  — https://law.justia.com/cases/new-jersey/appellate-division-published/2001/a3072-00-opn.html
- GDPR Art. 48 — transfers not authorised by EU law
  — https://gdpr-info.eu/art-48-gdpr/
