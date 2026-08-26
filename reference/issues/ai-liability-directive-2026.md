# ai-liability-directive-2026

**Issue:** A team deploys an AI system in the EU. A user is harmed by an AI-driven decision. The user sues. The team has no evidence disclosure process, no documentation trail, no fault-based liability defense. The case settles for the maximum.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

The EU AI Liability Directive (AILD) was proposed September 2022, updated July 2024, and **withdrawn in October 2025**. The replacement is the revised Product Liability Directive (PLD) (EU) 2024/2853 with explicit AI references. Teams still planning for AILD are working from a withdrawn proposal.

## Root cause

AILD's premise was procedural harmonization (evidence disclosure, burden-of-proof alleviation for fault-based claims against high-risk AI). It did not introduce strict liability; the proposal deferred that to a future review. After 3 years of negotiation, the Commission withdrew AILD in October 2025 and consolidated AI liability into the PLD.

## The 2026 liability landscape

| Instrument | Status | Scope | Effect |
|---|---|---|---|
| AI Liability Directive (AILD) | withdrawn October 2025 | n/a | no obligations |
| Product Liability Directive (PLD) (EU) 2024/2853 | adopted 2024, transposition by Dec 9, 2026 | defective products incl. software and AI | strict liability for manufacturers; applies to AI when placed on market after Dec 9, 2026 |
| Existing national fault-based liability | unchanged | all claims not covered by PLD | claimant proves fault, damage, causation |
| EU AI Act | in force since Aug 1, 2024 (phased) | high-risk AI systems | conformity assessment, documentation, monitoring obligations |

The PLD is the 2026 instrument to comply with for AI products.

## The PLD's AI rules

The revised PLD explicitly includes software and AI systems.

- **Definition of product:** encompasses software, including AI systems, when placed on the market or put into service after 9 December 2026
- **Liability:** strict liability (no fault required) for defective products causing harm
- **Strict liability trigger:** product is defective + damage + causal link
- **Defectiveness test:** product does not provide the safety a person is entitled to expect, or not the safety expected per purpose/marketing
- **Free / open-source exception:** FOSS developed or supplied outside commercial activity is not covered; narrow exception
- **Burden of proof:** claimant must show defectiveness plausibly; manufacturer must disclose evidence
- **Causation presumption:** if defect is established and damage is typically consistent with that defect, causation is presumed
- **Disclosure mechanism:** courts can order disclosure of relevant evidence by the manufacturer
- **Non-economic damage:** explicitly covered (pain and suffering, etc.)

The PLD covers both physical AI (robot) and software AI (LLM-based system) as long as it's placed on the market after Dec 9, 2026.

## The disclosure mechanism in detail

The PLD Article 4 introduces a disclosure mechanism that survives AILD's withdrawal.

- **Trigger:** claimant presents facts and evidence sufficient to support the plausibility of alleged defectiveness
- **Effect:** manufacturer must disclose evidence at its disposal relating to the alleged defectiveness
- **Scope:** technical documentation, training data records, test results, logs (subject to proportionality and confidentiality protections)
- **Sanction:** courts can impose sanctions for non-compliance (e.g., adverse inference)

This is the procedural protection AILD would have provided, now in PLD.

## The 4-step compliance pattern

1. **Document the AI system as a "product" under PLD.** Name it, version it, place it on the market with documentation.
2. **Maintain defect-prevention evidence.** Training data lineage, evaluation results, red-team reports, model card, monitoring logs.
3. **Establish an evidence disclosure process.** When a court orders disclosure, the team can produce documents in days, not months.
4. **Adopt a strict-liability reserve.** Strict liability is no-fault; the team should reserve for potential claims, not just defend them.

## The 3-actor liability chain

| Actor | Role | Liability |
|---|---|---|
| Manufacturer (developer of the AI system) | trained and placed the model on the market | strict liability under PLD |
| Importer | placed under their name on the EU market | strict liability under PLD |
| Authorized representative | designated by manufacturer for EU | strict liability under PLD |
| Deployer (end user) | uses the AI system in their service | fault-based liability under national law |

The manufacturer is the strict-liability target. The deployer may face fault-based claims in addition.

## The 5 anti-patterns

1. **Planning for AILD in 2026.** It was withdrawn. Plan for PLD instead.
2. **Assuming fault-based liability only.** PLD introduces strict liability for software AI products. The claimant doesn't have to prove fault.
3. **No documentation discipline.** Strict liability doesn't require fault, but it does require defectiveness. Document the design, testing, and monitoring to defend the defectiveness test.
4. **No evidence disclosure process.** When a court orders disclosure, the team has 30 days. The process must exist before the claim.
5. **Treating FOSS as a strict-liability shield.** The FOSS exception is narrow. If FOSS components are integrated into a commercial product, the exception doesn't apply.

## The interaction with EU AI Act

The EU AI Act (separate from PLD) imposes documentation, monitoring, and conformity assessment obligations on high-risk AI providers. PLD complements this with liability rules.

- **EU AI Act:** ex-ante obligations (before harm)
- **PLD:** ex-post liability (after harm)

The documentation required by EU AI Act (Article 11 technical documentation, Article 12 logs, Article 14 human oversight) is the same documentation PLD's disclosure mechanism would surface in litigation. Maintain the EU AI Act documentation; it's your PLD defense.

## The open questions (2026)

- **Software as product:** the PLD includes software, but the line between "software" and "service" is contested. An LLM API may be a service, not a product. The strict-liability protection may not apply.
- **FOSS scope:** the FOSS exception is narrow; case law will clarify. Watch for early 2027 decisions.
- **Causation presumption:** courts interpret "typically consistent" differently. A robust documentation trail helps argue for the presumption.
- **Damages cap:** PLD has no cap, but national law may impose caps for non-economic damage. The interaction is unsettled.

## Verification

The tell that PLD readiness is real:

- The AI system is documented as a "product" with version, release date, manufacturer
- EU AI Act documentation (Article 11, 12, 13) is maintained and versioned
- An evidence disclosure process exists and has been dry-run tested
- A defect-prevention evidence file is maintained (training data lineage, evals, red-team, monitoring)
- The team knows the strict-liability target (manufacturer, importer, authorized rep)

The tell it isn't:

- The team is planning for AILD
- No documentation discipline; "we'll figure it out if sued"
- No evidence disclosure process
- The team assumes fault-based liability only

## Gotchas

- **PLD applies to AI placed on the market after Dec 9, 2026.** AI systems placed before that date follow the old PLD (strict liability for physical products, fault-based for software).
- **The FOSS exception is narrow.** If your open-source library is integrated into a commercial AI system, the exception doesn't apply to the integrated product.
- **The disclosure mechanism is one-way.** The manufacturer must disclose; the claimant doesn't have to disclose their methodology.
- **Strict liability + insurance:** consider product liability insurance. PLD doesn't require it, but the cost of strict-liability claims makes insurance sensible.
- **National law variations:** each member state transposes PLD by Dec 9, 2026. National procedural rules vary. The harmonization is partial.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — high-risk category scope
- `issues/eu-ai-act-article-5-prohibited-2026.md` — prohibited practices
- `issues/eu-ai-act-ai-sandbox-2026.md` — regulatory sandbox
- `issues/ai-incident-disclosure-2026.md` — incident reporting triggers

## Source URLs (verified 2026-08-10)

- https://eur-lex.europa.eu/legal-content/ENG/TXT/?uri=cellex:3aac1ae1-0c2a-11ee-bd76-01aa75ed71a1 — PLD (EU) 2024/2853
- https://www.europarl.europa.eu/legislative-train/theme-a-europe-fit-for-the-digital-age/file-ai-liability-directive — AILD status (withdrawn)
- https://www.osborneclarke.com/insights/physical-ai-and-strict-liability-what-impact-eu-product-liability-directive
- https://data.consilium.europa.eu/doc/document/ST-12523-2024-INIT/en/pdf — AILD July 2024 updated version
- https://eur-lex.europa.eu/legal-content/ENG/TXT/?uri=cellar:16b4afba-3ff9-11ed-92ed-01aa75ed71a1 — original AILD proposal
- https://commission.europa.eu/topics/artificial-intelligence — Commission AI policy
- https://www.europarl.europa.eu/RegData/etudes/STUD/2024/762861/EPRS_STU(2024)762861_EN.pdf — EPRS impact assessment
