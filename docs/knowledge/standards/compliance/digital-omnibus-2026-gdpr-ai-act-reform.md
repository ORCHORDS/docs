# digital-omnibus-2026-gdpr-ai-act-reform

- **Issue**: The EU "Digital Omnibus" (proposed 19 November 2025, still in
  co-decision through mid-2026) is the biggest overhaul of GDPR since 2016 and
  simultaneously amends the AI Act and the Data Act. Teams either freeze
  compliance work "until the Omnibus lands" or ignore it entirely. Both are
  wrong. This is the tracker for what changes, what does not, and what to do
  while it is still a proposal.
- **Date**: 2026-08-13
- **Repo**: example-org/example-repo
- **Author**: kb-batch-3-compliance
- **Status**: Active; proposal in trilogue — monitor, do not plan on passage.

## What the Omnibus actually proposes

1. **GDPR new Art. 4a — AI training as legitimate interest.** Developing AI
   models on lawfully collected personal data becomes possible under
   legitimate interest if: (a) no systematic profiling of individual
   behaviour, (b) special-category data only with consent, (c) data subjects
   get an **opt-out right**, and (d) safeguards against identification.
2. **Storage-limitation relief.** Retaining personal data for AI training is
   generally NOT "excessive" for Art. 5(1)(e) purposes.
3. **Delayed transparency.** If informing data subjects at collection would
   compromise model security or trade secrets, you may inform within
   **3 months** instead of at collection.
4. **Cookie reform.** Browser-level consent signals plus legitimate interest
   for first-party audience measurement; end of forced cookie walls; consent
   validity extended (12-month model).
5. **AI Act timing.** Annex III high-risk obligations pushed to **Dec 2027**
   (Aug 2028 for some embedded systems); GPAI systemic-risk evaluation
   delayed; lighter documentation for smaller providers.
6. **Data Act.** Cloud-switching obligations trimmed.

The European Parliament adopted amendments on **16 June 2026** (keeping the
Annex III delay but restoring some consumer protections). Council and
Parliament positions still differ; nothing is final.

## Symptom

- A legal team says "GDPR changes are coming, pause the DPIA program until
  the Omnibus passes." Deadlines in force today are not paused by a proposal.
- A ML team reads a blog titled "GDPR allows AI training now" and starts
  scraping personal data under legitimate interest **today**. Art. 4a does not
  exist yet — current GDPR still governs, and litigation (e.g. pending
  LinkedIn/Meta scraping cases) still applies.
- Cookie banners get rebuilt to the *proposed* "12-month consent" model before
  any member state implements it — creating a current violation.
- Roadmaps drop the Aug 2026 AI Act milestone because "everything moves to
  2027." Only *some* Annex III items move; prohibitions, AI literacy, GPAI
  obligations, and Art. 50 transparency are **untouched**.

## Gotchas

- **A proposal is not law.** Every Omnibus provision above can be amended or
  dropped in trilogue. Build to current law; treat Omnibus relief as upside.
- **The opt-out in Art. 4a is load-bearing.** If the final text keeps it, you
  need a working opt-out channel (like DMA consent flows) BEFORE training,
  not a privacy-policy sentence. Retrofitting is the expensive path.
- **"Lawfully collected" is the entry ticket.** Art. 4a does not launder
  unlawfully scraped data. Collection basis still must be valid first.
- **Delayed transparency ≠ no transparency.** The 3-month window still
  requires the full Art. 13/14 information set — just later, with proof that
  immediate notice would harm security or secrets.
- **Special categories stay consent-locked** in every draft so far. Health,
  biometrics, politics in training data = consent or nothing.
- **The AI Act delay only moves Annex III high-risk timing.** Aug 2026
  obligations already live (Art. 50 disclosure, deepfake labels,
  machine-readable marks) do not move. Fines for live provisions are active.
- **The UK is not in the Omnibus.** UK GDPR/data-reform bill diverges
  separately; do not assume convergence.
- **Member-state laws do not auto-align.** Germany ( BDSG ), France, Italy
  can layer stricter national rules on whatever survives the Omnibus.

## Practical example — dual-track compliance

```text
TRACK A (enforced today — do now)
  Art. 50 chatbot/deepfake disclosures           (live 2 Aug 2026)
  AI literacy program                            (live 2 Feb 2025)
  GPAI transparency docs                          (live 2 Aug 2025)
  GDPR training basis = current law (consent or
  existing legitimate-interest test, documented LIA)

TRACK B (contingent — design for, trigger on adoption)
  Art. 4a training pipeline:
    - opt-out ingestion endpoint + suppression list keyed to
      pseudonymous IDs (never raw email) exported to training filter
    - special-category classifier in the data lake, quarantines
      Art. 9 data unless consent flag present
    - 3-month delayed-transparency template for Art. 14 notices
    - training-data provenance log (source, basis, opt-outs honored)
  Trigger: Official Journal publication + 20-day entry-into-force.
```

Re-review this file whenever a trilogue outcome is announced; the
`us-state-ai-laws-2026-*` and `eu-ai-act-*` files carry the unaffected
obligations in the meantime.
