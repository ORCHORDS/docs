# ai-procurement-2026

**Issue:** A vendor pitches an AI product to a US federal agency. The procurement officer asks for the model's bias test results, training data lineage, and red-team report. The vendor has a feature demo and a marketing brochure. The contract is awarded to a competitor with the documentation discipline.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

US federal AI procurement in 2026 requires a documented evidence package: model card, training data lineage, bias tests, red-team report, monitoring plan, governance documentation. Vendors without this lose contracts. The deadline is August 31, 2026 for 100% of AI performance claims to be mapped to benchmark artifacts per FAR 15.304.

## Root cause

The 2025 White House OMB M-25-21 (AI use) and M-25-22 (AI acquisition) memos established the rules. NIST's CAISI (Center for AI Standards and Innovation) and GSA's USAi platform are the enforcement infrastructure. The Federal Acquisition Regulation (FAR) is being updated to require AI-specific evidence.

## The 5 governing instruments

| Instrument | Issued | Effective | What it requires |
|---|---|---|---|
| OMB M-25-21 (AI use) | April 3, 2025 | 90-365 days | agencies must document governance, oversight, public trust controls |
| OMB M-25-22 (AI acquisition) | April 3, 2025 | Oct 1, 2025 (180 days) | new AI contracts must include AI-specific clauses |
| NIST CAISI + GSA USAi | March 18, 2026 partnership | ongoing | joint AI evaluation platform for federal use |
| DOE AL 2026-05 | May 8, 2026 | immediate | DOE-specific mandatory AI procurement policy |
| FAR revision (in progress) | 2026 | 2026-2027 | AI-specific FAR clauses for evidence and risk |

The compliance posture for a federal contractor: meet all 5, with the OMB memos as the floor and DOE AL as the agency-specific overlay.

## The 5-step vendor response pattern

GSA and NIST guidance (March 2026) recommends a 5-step response for vendors.

1. **Inventory claims within 5 days** (per FAR 15.304): list every AI claim in the proposal within 5 business days of draft solicitation review (accuracy, speed, safety, uptime, etc.)
2. **Map claims to evidence within 10 days** (per OMB M-25-21): connect each claim to a test artifact, data source, or governance document, including model version, dataset date, scoring method
3. **Run benchmark and red-team tests within 14 days**: at least 1 benchmark run + 1 adversarial or red-team test matching the solicitation
4. **Package evidence within 30 days** (per FAR 39.103 and FAR Part 15): one-page model summary, test logs, remediation notes, ready within 30 days of RFP release
5. **Re-test within 90 days of award** (for DoD, DHS, VA use cases): re-run tests within 90 days of award or system change so evidence stays current

This is the federal AI procurement clock. Plan backward from the RFP release.

## The 4 assurance gates (HAAF pattern)

The "Human Agency in AI-Driven Federal Acquisition" framework (NPS / DAIR 2026) defines 4 assurance gates that must be satisfied before AI capability is used.

- **Gate A — Intended use definition and data pedigree:** document purpose, decision boundaries, prohibited uses, data provenance (training sources, vendor attestations, data rights, privacy constraints, known limitations)
- **Gate B — Pre-deployment validation:** validate accuracy and robustness against benchmark, edge cases, failure modes
- **Gate C — Operational monitoring and human oversight:** monitoring plan, drift detection, human-in-the-loop checkpoints, override procedures
- **Gate D — Independent audit and accountability:** periodic independent audits, explainability artifacts (rationale, confidence, input-output mappings), administrative record retention

All 4 gates must be satisfied before deployment.

## The minimum governance contract terms

For AI acquisitions, the contract should include these minimum terms.

- **Model and prompt configuration control and version disclosure**
- **Logging requirements and data retention for audit purposes** (typically 3-7 years)
- **Performance monitoring and drift notification** (alert thresholds, response SLAs)
- **Security testing for adversarial threats** (red-team, jailbreak testing)
- **Incident response and disclosure obligations**
- **Bias and fairness testing** with documented results
- **Human oversight requirements** with override procedures
- **Subcontractor flow-down** for any AI components in the supply chain

The contract should be specific (concrete metrics, named benchmarks, named datasets) not aspirational.

## The 5 anti-patterns

1. **Marketing claims without test artifacts.** "Best in class accuracy" without a benchmark citation is now a FAR violation.
2. **No training data lineage.** AI Impact Assessment (AIIA) under DOE AL requires data pedigree. Vendors without lineage lose the bid.
3. **One-time testing.** Tests are per-quarter or per-system-change. The 90-day re-test is mandatory for many agencies.
4. **No independent audit.** Self-attestation is not enough. The HAAF Gate D requires independent verification.
5. **Generic AI clauses.** Per the RopesGray 2025 analysis, agencies may not harmonize around NIST; specific contract language matters.

## The AI use disclosure requirement

The DAIR / NPS framework also requires AI use disclosure in the proposal.

- **What AI was used:** model name, tool name, version
- **When:** date, time, configuration
- **Why:** purpose (substantive content generation, automated analysis)
- **Attestation:** contractor attests factual claims were human-verified

This applies to AI used in the proposal preparation itself, not just the AI product being procured. The "AI in the bid" disclosure is becoming standard.

## The cross-jurisdiction procurement landscape

| Jurisdiction | Procurement framework |
|---|---|
| US federal | OMB M-25-21/22, FAR revision, CAISI/USAi, agency ALs |
| US state | varies; California requires frontier AI framework for procurement |
| EU | EU AI Act high-risk requirements apply to public procurement |
| UK | Algorithmic Transparency Recording Standard (ATRS) for public sector |
| Canada | Directive on Automated Decision-Making |
| Australia | AI in government policy |

For a global vendor: build the US federal evidence package, then map to other jurisdictions. The US package is the most demanding.

## The budget reality

The GSA guidance (March 2026) recommends $25,000-$100,000 per RFP cycle for third-party validation, red-teaming, and documentation. This is the cost of competing for federal AI contracts. Vendors who can't budget this lose the bid.

## Verification

The tell that AI procurement readiness is real:

- An evidence package (model card, training data lineage, bias tests, red-team, monitoring) is ready
- The 5-step vendor response pattern is on a checklist with deadlines
- The 4 assurance gates (HAAF) are documented for each AI product
- Contract clauses include model versioning, logging, drift notification, incident response
- The 90-day re-test is scheduled, not ad-hoc

The tell it isn't:

- Marketing brochure only, no test artifacts
- "We'll generate the evidence when we have the contract"
- No training data lineage
- No third-party audit

## Gotchas

- **FAR 15.304 deadline is August 31, 2026** for 100% of AI performance claims to be mapped to benchmark artifacts. After that date, unmapped claims are a FAR violation.
- **DOE AL 2026-05 is mandatory**, not advisory. DOE contractors must comply.
- **The 90-day re-test applies to DoD, DHS, VA use cases** specifically; other agencies may have different cadences.
- **M-25-22 applies to contracts awarded or renewed 180 days after issuance** (i.e., on or after Oct 1, 2025). Older contracts may not be in scope.
- **The AI use disclosure in proposals** is becoming standard; vendors that don't disclose may be disqualified for non-compliance.

## Related

- `issues/ai-bill-of-rights-2026.md` — federal US AI policy context
- `compliance/` — regulatory compliance patterns
- `worktree/sbom-slsa-2026.md` — supply chain evidence that overlaps with procurement evidence
- `lessons/ai-observability-otel-2026.md` — observability for the monitoring requirement

## Source URLs (verified 2026-08-10)

- https://www.whitehouse.gov/omb/information-technology/omb-m-25-21/ — M-25-21
- https://www.whitehouse.gov/omb/information-technology/omb-m-25-22/ — M-25-22
- https://www.gsa.gov/about-gsa/newsroom/news-releases/gsa-and-nist-partner-to-boost-ai-evaluation-science-in-federal-procurement-03182026
- https://www.energy.gov/sites/default/files/2026-05/AL%202026-05%20Unbiased%20AI%20Principles%20M-26-04_5.8.26.pdf — DOE AL 2026-05
- https://www.nist.gov/itl/ai-risk-management-framework
- https://www.dair.nps.edu/bitstream/123456789/5517/1/SYM-AM-26-080.pdf — HAAF framework
- https://govcontractfinder.com/contracting-technology/nists-new-ai-evaluation-platform-contractors-care-2026
- https://www.ropesgray.com/en/insights/alerts/2025/04/white-house-issues-guidance-on-use-and-procurement-of-artificial-intelligence-technology
- https://www.acquisition.gov/far/15.304 — FAR 15.304 (proposal evaluation)
- https://www.acquisition.gov/far/39.103 — FAR 39.103 (contractor performance assessment)
