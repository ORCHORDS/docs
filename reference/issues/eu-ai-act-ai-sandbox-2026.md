# eu-ai-act-ai-sandbox-2026

**Issue:** A startup builds an innovative AI system for credit scoring. The EU AI Act classifies it as high-risk. Conformity assessment takes 6 months. The startup needs to test in real-world conditions now, not after the conformity assessment.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Act has been in force for high-risk provisions since August 2026 (with Digital Omnibus pushing standalone Annex III to 2 December 2027). For an innovative AI system that needs real-world testing before market placement, the conformity assessment can take 6-9 months. The startup has no path to test in the real world without triggering compliance obligations.

## Root cause

Article 57 establishes AI regulatory sandboxes — controlled environments where innovative AI systems can be developed, trained, tested, and validated before market placement, under regulatory supervision. Member States must establish at least one national sandbox, operational by **2 August 2026**. The sandbox allows real-world testing with regulatory guidance, without administrative fines for infringements of the AI Act, provided the provider follows the sandbox plan.

## The 9 Article 57 objectives

1. Improving legal certainty for regulatory compliance
2. Supporting best-practice sharing through cooperation
3. Fostering innovation and competitiveness
4. Contributing to evidence-based regulatory learning
5. Facilitating market access, especially for SMEs and start-ups
6. (Implied) Real-world testing under controlled conditions
7. (Implied) Early identification of risks
8. (Implied) Supervised development of high-risk systems
9. (Implied) Cross-border cooperation

The sandbox is not a compliance bypass. It is a controlled environment with regulatory oversight and defined exit criteria.

## The eligibility criteria

To participate in a national AI sandbox, the provider or prospective provider must:

- Have an innovative AI system intended for development, training, testing, or validation
- Submit a sandbox plan to the competent authority
- Follow the plan in good faith
- Accept regulatory guidance
- Cooperate with the authority on risk identification and mitigation

The plan includes: the system's purpose, the testing scope, the duration, the data sources, the risk mitigation measures, and the exit criteria.

## The real-world testing (Article 60)

Beyond the sandbox, Article 60 allows real-world testing of high-risk AI systems outside sandboxes, subject to a real-world testing plan approved by the market surveillance authority:

```python
# Real-world testing conditions (Article 60(4))
conditions = {
    "plan_submitted": True,  # (a) plan submitted to MSA
    "plan_approved": True,   # (b) approved or tacit approval after 30 days
    "registration": True,    # (c) registered with EU-wide unique ID
    "eu_established": True,  # (d) provider established in EU or has legal rep
    "data_transfer_safeguards": True,  # (e) third-country transfers compliant
    "duration_max_6_months": True,  # (f) max 6 months, extendable +6
    "vulnerable_protected": True,  # (g) vulnerable subjects protected
    "deployer_informed": True,  # (h) deployers informed of test aspects
    "informed_consent": True,  # (i) subjects consented
    "qualified_oversight": True,  # (j) qualified personnel supervise
    "reversible": True,  # (k) decisions can be reversed
}
```

The 6-month cap (extendable to 12) prevents indefinite real-world testing. After 12 months, the system must either enter the market (with full compliance) or be retired.

## The 5 sandbox benefits

1. **Legal certainty** — guidance from the competent authority before market placement
2. **Real-world testing** — actual user conditions, not synthetic
3. **No administrative fines for AI Act breaches** during the sandbox, provided the plan is followed
4. **Cross-border cooperation** — multiple Member States can run a joint sandbox
5. **Priority access for SMEs and start-ups** — Article 57(1) mentions participation should be accessible, with specific measures for SMEs

The "no administrative fines" carve-out is significant. The provider still has liability under national tort law for damage caused; the sandbox does not waive third-party claims. But the EU AI Act's own penalties are paused during good-faith sandbox participation.

## The exit pathways

The sandbox has a defined end. The provider and authority agree on exit criteria upfront:

- **Market placement** — system graduates to full Annex III compliance
- **Iterate and return** — system returns to sandbox with new plan
- **Retire** — system is shelved or repurposed outside EU AI Act scope
- **Pivot to non-high-risk** — system is re-architected to fall below Annex III

A team that uses the sandbox to validate a high-risk system must commit to one of these exit pathways. The sandbox is not a permanent safe harbor.

## The national competent authority

Each Member State designates competent authorities responsible for:

- Establishing the national sandbox (or participating in a joint one)
- Reviewing and approving sandbox plans
- Providing guidance during the sandbox
- Receiving incident reports during real-world testing
- Submitting annual reports to the AI Office

As of mid-2026, the European AI Office is coordinating the rollout. National implementations vary; the Digital Omnibus affects only some timelines.

## The joint sandbox model

Article 57(1) allows joint sandboxes established by the competent authorities of multiple Member States. This is the recommended model for cross-border AI systems:

- One sandbox plan, multiple jurisdictions
- Coordinated guidance from national authorities
- Common exit pathway

For a high-risk AI system deployed in 5 EU countries, a joint sandbox avoids 5 separate national sandbox applications.

## The reporting obligation

National competent authorities submit annual reports to the AI Office and the Board, from one year after sandbox establishment. The reports include:

- Progress and results
- Best practices
- Incidents
- Lessons learned
- Recommendations on setup, application, and possible revision of the regulation

The reporting feeds back into the AI Act's annual review cycle (Article 112). A practice that works in one sandbox may inform the Commission's review of Annex III or Article 5.

## The Article 60 real-world testing distinction

Article 57 (sandboxes) and Article 60 (real-world testing) are different mechanisms:

| | Article 57 sandbox | Article 60 real-world testing |
|---|---|---|
| Environment | Controlled, supervised | Actual market conditions |
| Approval | Sandbox plan with authority | Real-world testing plan with MSA |
| Duration | Per sandbox plan | Max 6 months (+6) |
| Scope | Development, training, testing, validation | Pre-market testing only |
| Fines | No AI Act fines during good-faith participation | Standard AI Act applies |

Use Article 57 for development and pre-deployment testing. Use Article 60 for the final pre-market validation in real conditions. Both can apply to the same system at different lifecycle stages.

## Verification

The tell that sandbox strategy is working:

- Innovative high-risk systems have a documented sandbox plan before development
- Real-world testing plans are approved before any external testing
- The provider is in good-faith compliance with the sandbox plan (no shortcuts)
- Exit criteria are defined upfront
- Annual reports to the AI Office are filed
- The team can name the national competent authority for their jurisdiction

The tell it isn't:

- A team tests in production because the sandbox "takes too long"
- Real-world testing exceeds 12 months without a market placement plan
- The provider deviates from the sandbox plan without notifying the authority
- No exit criteria documented
- A team cannot name the national authority

## Gotchas

- **Sandbox plan must be followed in good faith.** Deviation restores the fine exposure.
- **Sandbox does not waive tort liability.** Third-party damage claims still apply.
- **The duration cap is 12 months for real-world testing.** After that, the system must be in market or retired.
- **Member State implementation varies.** The substantive rules are harmonized; the procedural details are national.
- **Joint sandboxes are recommended for cross-border.** Avoid 5 separate national applications.
- **Article 57 and Article 60 are distinct mechanisms.** Use both, in sequence.
- **SMEs and start-ups have priority access.** Larger companies may be deprioritized.
- **The exit pathway is not optional.** A team must graduate, iterate, retire, or pivot.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — full Act
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `issues/eu-ai-act-article-5-prohibited-2026.md` — what's banned
- `issues/fria-template-2026.md` — fundamental rights assessment

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/57/
- https://artificialintelligenceact.eu/article/60/
- https://www.europarl.europa.eu/thinktank/en/document/EPRS_ATA(2026)785673
- https://www.europarl.europa.eu/cmsdata/305017/AI%20regulatory%20sandboxes%201.pdf
- https://www.europarl.europa.eu/meetdocs/2024_2029/plmrep/COMMITTEES/LIBE/DV/2026/03-18/FinalCAs-AIOmnibus_16032026_EN.pdf
