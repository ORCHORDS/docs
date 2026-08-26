# US State Privacy Laws 2026 — Multi-State Compliance for Developers

> When: 2026 is a watershed year for US state privacy laws. Several new
> comprehensive laws took effect on Jan 1, 2026; more roll out across the
> year. As of mid-2026 there is still no federal comprehensive privacy law,
> so compliance means following the strictest applicable state rules.
> Who: Any developer whose product is available to US residents and meets a
> state law's thresholds (typically based on revenue, data volume, or sale of
> personal data). The strictest state often governs de facto.

## Landscape — New Laws Effective in 2026

The following state comprehensive privacy laws took effect (or take effect)
in 2026. Each has its own definitions, thresholds, and consumer rights:

- **Delaware Personal Data Privacy Act (DPDPA)** — effective Jan 1, 2026.
  Low thresholds: applies to entities controlling/processing personal data of
  35,000+ consumers OR 10,000+ consumers if deriving revenue from data sale.
  Broad "consumer" definition EXCLUDES people acting in an employment
  context, which is narrower than some other state laws.
- **Nebraska Data Privacy Act** — effective Jan 1, 2026. Mirrors much of
  the Texas/Tennessee model. No revenue threshold, but a 100,000-consumer
  data-volume threshold (or 25,000 + revenue from data sale).
- **New Hampshire Privacy Act** — effective Jan 1, 2026. 35,000-consumer
  threshold.
- **New Jersey Data Privacy Act (NJDPA)** — effective Jan 15, 2025, but
  **enforcement began ramping in 2026**. Stricter than many peers: includes
  sensitive-data category, mandatory privacy notice, and a 15-day breach
  notification window.
- **Tennessee Information Protection Act (TIPA)** — effective Jul 1, 2025;
  enforcement scrutiny intensifying through 2026. Notable for requiring a
  "reasonable" privacy program with documented risk assessments.
- **Minnesota Consumer Data Privacy Act (MCDPA)** — effective Jul 31, 2025,
  with cure period expiring in 2026. Notable: includes private right of
  action for certain violations (rare among state laws).
- **Maryland Online Data Privacy Act (MODPA)** — effective Oct 1, 2025.
  Stricter than most: **prohibits** the sale of sensitive data outright
  (not just opt-out), and restricts "data brokers" more tightly.
- **Indiana, Kentucky, Rhode Island** — additional laws taking effect
  across 2026 with varying thresholds.

Plus the existing 2023-2025 cohort that remain live: California (CCPA/CPRA),
Colorado, Connecticut, Virginia, Utah, Texas (broad applicability), Oregon,
Montana, Florida.

## Symptom

A SaaS startup launches in early 2026. The team writes a single CCPA-style
privacy notice, ships a "Do Not Sell My Personal Information" link pointing
to an email address, and assumes compliance because "California is the
strictest state." Six months later, a Maryland user files a complaint: the
product sold their sensitive data (including precise geolocation) under an
"opt-out" model — but MODPA **prohibits** sale of sensitive data outright.
There is no opt-out cure. This is a direct violation.

## Core Developer Obligations (Multi-State Synthesis)

Treat the strictest requirement across all applicable states as your floor:

1. **Privacy notice** — must be clear, conspicuous, and updated regularly.
   Must disclose: categories of data collected, purposes, third-party
   sharing, consumer rights, how to exercise them, and the appeal process.
   Maryland and New Jersey require additional specificity around sensitive
   data handling.
2. **Consumer rights implementation** — at minimum: access, deletion,
   correction, data portability, opt-out of sale, opt-out of targeted
   advertising, opt-out of profiling. Build a single API that satisfies the
   strictest state's response timeframe (45 days is common; some allow
   extensions).
3. **Sensitive data** — obtain **opt-in consent** (not opt-out) before
   processing sensitive data (racial/ethnic origin, religious belief,
   health, biometric, precise geolocation, children's data). Maryland
   prohibits sensitive-data sale outright.
4. **Universal opt-out signals** — Colorado, Connecticut, California (via
   CPRA regs) require recognising GPC (Global Privacy Control) browser
   signals. Treat them as binding opt-out requests.
5. **Data protection assessments (DPAs)** — required by Colorado, Virginia,
  Connecticut, Maryland, New Jersey, and others for high-risk processing
  activities (targeted advertising, sensitive data, profiling, sale).
6. **Children's data** — heightened requirements. COPPA federal floor plus
  state-specific age-appropriate design duties (California Age-Appropriate
  Design Code, Maryland's age-appropriate rules).
7. **Vendor contracts** — flow down obligations to processors via data
   processing agreements. Several states make controllers liable for
   processor failures without a DPA in place.
8. **Breach notification** — each state has its own clock. New Jersey:
   15 days. Most others: 30-60 days. Track the SHORTEST applicable clock.

## Gotchas

- **Texas has no threshold.** The Texas Data Privacy and Security Act
  applies to virtually anyone doing business in Texas that processes
  personal data — no minimum data volume, no minimum revenue. If you have
  Texas users, you're in scope.
- **Maryland prohibits sensitive-data sale.** Not opt-out. PROHIBITED. If
  your business model involves selling sensitive data (including precise
  geolocation), you need a different model for Maryland users or a different
  model altogether.
- **"Sale" is defined broadly.** It includes exchanging data for monetary OR
  "other valuable consideration." Sharing data with analytics providers in
  exchange for services can be a "sale" under some state definitions.
  California's is the broadest; assume your "data sharing" is a sale unless
  you can prove otherwise.
- **GPC is binding, not optional.** If a user sends a GPC signal, you must
  honour it as an opt-out of sale AND targeted advertising. Failure to
  implement GPC recognition is a per-violation risk in multiple states.
- **Minors' data triggers stricter rules even if COPPA isn't in play.**
  California's Age-Appropriate Design Code applies to products "likely to be
  accessed by children" — broadly interpreted. Maryland applies similar
  duties. Do not wait for actual knowledge of a child user.
- **Private rights of action are expanding.** Most state laws do NOT grant a
  private right of action (only AG/enforcement agency can sue), but
  Minnesota's MCDPA and some litigation theories under existing laws create
  direct exposure. Track this carefully.
- **Cure periods are expiring.** Many state laws offered a 30-day cure
  period for violations; several expired in 2026. Without a cure period,
  violations are immediately actionable. Update your compliance accordingly.
- **Employment data is treated differently.** Some laws (Virginia,
  Connecticut originally) excluded employment/B2B data; others (California
  via CPRA, New Jersey) include some or all employment context. Do not
  assume "employee data is exempt everywhere" — that changed in 2023 and
  continues to narrow.
- **Data brokers must register.** California, Vermont, Oregon, Texas, and
  others require data brokers to register with the state. Failing to
  register can trigger penalties independent of any underlying violation.
- **Enforcement is active.** State AGs are publishing enforcement
  priorities for 2026. Common targets: dark patterns in consent flows,
  GPC non-compliance, sensitive-data handling, and children's data.

## Multi-State Compliance Strategy

1. **Map your data flows.** Know what you collect, from whom, for what
   purpose, where it goes, and how long you keep it. This is non-negotiable
   — you cannot comply without it.
2. **Build to the strictest floor.** Implement the strictest combination:
   Maryland-style sensitive-data prohibition, Colorado-style GPC
   recognition, New Jersey-style 15-day breach clock.
3. **Automate consumer rights responses.** Manual response is not scalable
   across states. Build a single workflow that meets the strictest
   timeline.
4. **Maintain a state-by-state matrix.** Track thresholds, effective dates,
  cure-period status, sensitive-data definitions, and breach clocks.
5. **Conduct data protection assessments.** Document them. They are required
   by multiple states and double as audit evidence.
6. **Update privacy notices on a cadence.** Laws change; notices must keep
   up. Quarterly review is a reasonable baseline for 2026.
