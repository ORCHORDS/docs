# EU AI Act Annex III High-Risk AI Systems — August 2026 Enforcement

> When: The critical deadline for most enterprises is **August 2, 2026**, when
> Annex III high-risk AI system requirements become applicable. Some deadlines
> are under active postponement proposals (as of mid-2026), but treat them as
> live — enforcement can still target systems already on the market.
> Who: Developers, providers, and deployers of high-risk AI systems offered or
> used in the EU, regardless of where the company is headquartered.

## Scope — What Counts as "High-Risk" (Annex III)

Annex III enumerates specific use-cases that are automatically high-risk:

- **Biometrics**: remote biometric identification, biometric categorisation
  by sensitive attributes, emotion recognition (with narrow exceptions).
- **Critical infrastructure**: AI used as a safety component in road, rail,
  water, gas, heating, electricity.
- **Education and vocational training**: automated admissions scoring,
  exam proctoring, student performance evaluation.
- **Employment and worker management**: résumé screening, performance
  monitoring, promotion/termination decision-support.
- **Essential services**: creditworthiness scoring, credit denials,
  insurance risk pricing and eligibility.
- **Law enforcement**: risk assessment of individuals, polygraph/emotion
  analysis, evidence reliability scoring, profiling.
- **Migration, asylum, border control**: eligibility assessment, security
  risk scoring, polygraph analysis.
- **Justice and democratic processes**: legal research assistance, fact
  pattern matching, election influence-related systems.

If your AI system touches ANY of these, you are high-risk under Annex III.
There is no de minimis exemption based on company size.

## Symptom

A product team ships a résumé-screening model (clearly Annex III employment
use-case) into the EU market without having done a conformity assessment,
built technical documentation, or registered the system in the EU database.
The system is live for weeks. Nobody flagged it as high-risk because "we're
just a startup" and "it's only used for ranking, humans make the final call."

This is a violation. The human-in-the-loop "defence" does NOT downgrade a
system from high-risk. The fine ceiling is €15M or 3% of global turnover
(whichever is higher) for Annex III violations, and €35M / 7% for
prohibited-practice overlap.

## Developer Obligations (Annex III Providers)

As the provider of a high-risk system you must, before placing it on the
market or putting it into service:

1. **Conformity assessment** — perform and document it. For most Annex III
   systems this is a **self-assessment** (no notified body required), EXCEPT
   biometric systems, which require notified-body involvement.
2. **Technical documentation** (Annex IV) — architecture, training data
   description, data governance practices, bias mitigation, performance
   metrics, logging capabilities.
3. **Risk management system** — iterative, lifecycle-wide, continuous.
4. **Data and data governance** — training/validation/test datasets must be
   relevant, sufficiently representative, free of errors, and relevant to the
   intended purpose.
5. **Technical documentation and record-keeping** — automatic event logging
   for the system's operational lifetime.
6. **Transparency and information for deployers** — instructions for use must
   disclose system limitations and the supervising human's role.
7. **Human oversight** — design the system so a natural person can
   effectively supervise. Oversight must be built into the system, not just
   described in a manual.
8. **Accuracy, robustness, cybersecurity** — design with resilience to
   errors, faults, inconsistencies, and adversarial attacks.
9. **Quality management system** — documented, audited.
10. **Automatic logging** — events that allow monitoring of the system's
    operation relative to its intended purpose.
11. **Corrective actions and duty of information** — report serious incidents
    to the market surveillance authority.
12. **CE marking and EU database registration** — the system must be
    registered in the EU database before deployment.

## Deployer Obligations (Distinct from Provider)

If you USE a high-risk system (you didn't build it) you still have duties:

- Use it **only for its intended purpose**.
- Provide **human oversight** — assign competent, trained, authorised people.
- Monitor operation and **suspend use** if it presents a risk.
- Keep **automated logs** for at least 6 months (longer if regulated).
- Report **serious incidents** to the provider AND the market surveillance
  authority within strict timeframes.
- Perform a **fundamental rights impact assessment** (FRIA) before first use
  for certain public-sector or biometric deployers.

## Gotchas

- **"We don't sell to the EU" is not a defence.** If an EU-based deployer
  uses your system, or if outputs affect people in the EU, the AI Act's
  extraterritorial reach applies. This mirrors GDPR's market-effects test.
- **The Aug 2026 deadline may be postponed** — as of mid-2026 there are
  proposals to push back some Annex III obligations. DO NOT plan around
  postponement. Build to the current deadline; postponement is a gift, not a
  strategy. The regulatory debt compounds.
- **Fine-tuning a foundation model does not make it "your own" low-risk
  system.** If the fine-tuned system is deployed in an Annex III use-case,
  the high-risk obligations apply to you as provider of the fine-tuned system.
- **Human-in-the-loop is an oversight requirement, not a classification
  escape hatch.** It must be genuine, effective, and documented — a rubber-
  stamp click-through is not compliance.
- **The conformity assessment is not a one-time gate.** It must be re-run on
  **substantial modification** — including retraining with new data that
  changes behaviour in ways not covered by the original assessment.
- **Logging is mandatory from first deployment.** Teams that add logging
  later cannot retroactively evidence the pre-logging period, which makes any
  incident report from that period non-credible.
- **Open-source exemption is narrow.** It covers AI released under a license
  allowing open access AND not placed on the market as a paid service. Most
  commercial open-source AI does NOT qualify — if you charge for hosting,
  tuning, or enterprise use, you are a provider.
- **The EU database registration requirement applies BEFORE first use**, not
  before first sale. A pilot with one EU customer still triggers it.
- **Serious incident reporting has a 15-day clock** (2 days for
  fatalities/multiple injuries). There is no "we were still investigating"
  grace period — file preliminary, update later.
- **GDPR and the AI Act overlap, they do not substitute.** A DPIA under
  GDPR Art. 35 is NOT the same as the AI Act risk management system. You
  must do both. A single combined document is acceptable but it must
  explicitly address both regimes' required contents.

## Checklist Before August 2, 2026

- [ ] Inventory every AI system you ship or operate; classify each against
  Annex III.
- [ ] For each high-risk system: technical documentation (Annex IV) drafted.
- [ ] Risk management system established and documented (iterative, lifecycle).
- [ ] Logging infrastructure in place and tested BEFORE go-live.
- [ ] Human oversight design documented; named accountable humans assigned.
- [ ] Conformity assessment performed; CE marking affixed.
- [ ] EU database registration completed.
- [ ] Instructions-for-use documentation ready for deployers.
- [ ] Serious-incident reporting workflow built with the 15-day clock.
- [ ] DPIA completed in parallel if personal data is processed (likely yes).
- [ ] FRIA completed if you are a public-sector or biometric deployer.
