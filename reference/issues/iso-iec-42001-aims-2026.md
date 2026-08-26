# iso-iec-42001-aims-2026

**Issue:** A team has implemented an AI system. Customers ask "are you ISO 42001 certified?" The team says no. Procurement requires it for enterprise deals. The team has 3-6 months to certify.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

ISO/IEC 42001:2023 is the world's first certifiable management system standard for AI. It defines requirements for an Artificial Intelligence Management System (AIMS). Customers in regulated industries (finance, healthcare, public sector) increasingly require ISO 42001 certification as a procurement condition. ISO 42006:2025 sets the requirements for certification bodies, tightening audit quality in 2025-2026.

## Root cause

ISO 42001 is not a model-testing standard, not a bias-measurement protocol, and not a technical benchmark. It is the organizational scaffolding around AI: who is accountable, how risks and impacts are assessed, how systems move through their lifecycle, where the data comes from, and what is told to affected people.

It follows the same Clause 4-10 structure as ISO 27001, with 38 Annex A controls grouped into 9 themes (A.2-A.10). Certification runs gap analysis → documentation → impact assessments → implementation → internal audit → Stage 1 → Stage 2. A focused scope takes 3-6 months.

## The mandatory structure (Clauses 4-10)

| Clause | Requirement |
|---|---|
| 4. Context of the organization | Define role in AI value chain (provider, deployer, both), internal/external issues, interested parties, scope of AIMS |
| 5. Leadership | Top management owns the AI policy, assigns roles and responsibilities, demonstrates commitment |
| 6. Planning | AI risk assessment (6.1.2), AI system impact assessment (6.1.4), risk treatment with Statement of Applicability against Annex A, measurable AIMS objectives |
| 7. Support | Resources, competence, awareness, communication, documented information |
| 8. Operation | Execute plans: operational controls over AI lifecycle, re-run risk/impact assessments on significant change |
| 9. Performance evaluation | Monitoring/measurement, internal audit of AIMS, management review with AI-specific inputs |
| 10. Improvement | Nonconformity handling, corrective action, including for AI incidents (hallucination-driven errors, drift, misuse) |

## The 38 Annex A controls (9 themes)

| Theme | What it requires |
|---|---|
| A.2 AI policies | Written AI policy, alignment with organizational purpose |
| A.3 Roles and responsibilities | AI system owner, AIMS coordinator, AI reviewer (with authority to halt) |
| A.4 Competence and training | Competency levels per role; training proportionate to exposure |
| A.5 Planning and impact assessment | AI risk assessment, AI system impact assessment |
| A.6 AI system lifecycle | Design, development, deployment, operation, decommissioning controls |
| A.7 Data for AI systems | Data inventory, quality criteria, access controls, provenance, privacy |
| A.8 Third-party and customer relationships | Supplier assessment, contractual AI requirements |
| A.9 Incident management, continuity | Incident response, business continuity, AI-specific scenarios |
| A.10 Documentation and records | AI system documentation, logging, traceability |

Each control is selected and justified via the Statement of Applicability. Unlike a policy document, each selected control must produce operating evidence.

## The certification timeline

For a focused scope — say, a SaaS company with 3-5 AI systems — expect 3-6 months end to end. Larger enterprises with sprawling AI estates should plan 9-12 months.

| Phase | Duration | Activities |
|---|---|---|
| Gap analysis | Weeks 1-2 | Inventory every AI system (including shadow GenAI), map against Clauses 4-10 and Annex A, define defensible scope |
| AIMS documentation | Weeks 3-6 | AI policy, roles, risk and impact methodologies, lifecycle procedures, data management, Statement of Applicability |
| Risk and impact assessments | Weeks 5-8 | Run Clause 6.1.2 risk assessment and 6.1.4 impact assessment for each in-scope system |
| Implementation | Weeks 8-16 | AI inventory, lifecycle stage gates, logging, supplier relationships, training, human oversight per system |
| Internal audit and management review | Weeks 14-18 | Full internal audit by someone independent of implementation; management review with documented decisions |
| Stage 1 audit | 2-4 weeks | Certification body reviews documentation and readiness (usually remote) |
| Stage 2 audit | 2-4 weeks | Interviews with leadership, engineers, system owners; sampling of impact assessments, lifecycle evidence, logs, supplier files |

On successful conclusion: certificate issued for 3 years with annual surveillance audits.

## The cross-mapping to other frameworks

| ISO 42001 control area | ISO 27001 equivalent | GDPR article | Reusable? |
|---|---|---|---|
| Data access controls (A.7.3) | A.9 Access Control | Art. 25 (Privacy by design) | Yes, extend existing |
| AI policy (A.2) | A.5.1 Information security policies | Art. 5 (accountability) | Yes, adapt |
| Supplier assessment (A.10) | A.15 Supplier relationships | Art. 28 (processor) | Yes, extend |
| Incident management (A.9) | A.16 Incident management | Art. 33 (breach notification) | Yes, extend |
| Logging and traceability (A.6) | A.12.4 Logging | Art. 30 (records of processing) | Yes, extend |

A team that holds ISO 27001 has a substantial head start; the AIMS is an extension of the ISMS, not a replacement. Integration cuts the implementation work substantially.

## The EU AI Act cross-mapping

| EU AI Act classification | ISO 42001 control intensity | Key controls required |
|---|---|---|
| **Prohibited** (Art. 5) | N/A — system must not exist | Clause 4.3 scope exclusion + legal sign-off |
| **High-risk** (Annex III) | Full Annex A implementation | A.3, A.4, A.5, A.6, A.7, A.8, A.9, A.10 all required |
| **GPAI with systemic risk** | Full + adversarial testing | A.6, A.7, A.9 with enhanced monitoring |
| **Limited risk** | Lightweight | A.2, A.6, transparency only |
| **Minimal risk** | Voluntary | None mandatory |

ISO 42001 certification demonstrates that AI governance processes meet the standard's requirements; it does not constitute a conformity assessment under the EU AI Act. The two are complementary, not substitutive.

## The cost

Certification body fees in 2026 for a mid-market organization are approximately:

- Stage 1 + Stage 2 initial certification: **EUR 8,000 - 18,000**
- Annual surveillance audit: **EUR 4,000 - 9,000**
- Consulting and implementation: **EUR 15,000 - 50,000** depending on scope

For a small organization (under 100 employees) with a focused scope (3-5 AI systems), total first-year cost is typically EUR 30,000 - 80,000. For large enterprises, EUR 200,000 - 500,000+.

## The voluntary status

Nobody is legally required to hold an ISO 42001 certificate today. It is voluntary. But:

- Customers in regulated industries increasingly require it
- US federal contractors reference it via NIST AI RMF cross-mapping
- EU AI Act conformity assessment preparation reuses ISO 42001 documentation
- Insurance providers offer reduced premiums for ISO 42001-certified organizations

The standard is positioned to become the de facto governance standard for AI, similar to how ISO 27001 became the de facto information security standard.

## The extension to existing ISMS

You cannot simply extend an ISO 27001 certificate to cover AIMS. A separate ISO 42001 audit is required. The Clauses 4-10 structure is parallel, not shared; the Annex A controls are AI-specific.

However, the implementation can share infrastructure: the same governance committee, the same internal audit function, the same management review process. The shared infrastructure reduces the marginal cost of AIMS significantly for ISO 27001-certified organizations.

## Verification

The tell that ISO 42001 implementation is working:

- A scope statement is signed by top management
- An AI inventory with risk levels and owners exists
- Impact assessments (Clause 6.1.4) are run for each in-scope system, signed by the AIMS coordinator
- Internal audit runs annually; findings are documented; corrective actions are tracked to completion
- Management review inputs include AI incidents, drift, third-party risks
- The certificate is held and current; surveillance audits pass

The tell it isn't:

- "We're working toward ISO 42001" with no scope statement
- An AI inventory that has not been updated since the initial gap analysis
- Impact assessments that are template-filled, not substantively applied
- Internal audit has never run
- Surveillance audit finds major nonconformities

## Gotchas

- **Scope statement is critical.** Excluding a high-risk AI system from the scope is a finding; auditors will challenge scope that quietly excludes the most risky systems.
- **Impact assessments must name real people who could be harmed.** "Reputational risk: medium" is not an impact assessment. Auditors test reality against paper.
- **ISO 27001 integration is high but not free.** A separate ISO 42001 audit is required; the implementation shares infrastructure, not certification.
- **The certificate is for 3 years with annual surveillance.** Surveillance audits are not optional; missing one suspends the certificate.
- **ISO 42001 does not satisfy EU AI Act conformity assessment.** The two are complementary, not substitutive.
- **The 3-6 month timeline is for a focused scope.** A 50-AI-system enterprise should plan 12-18 months.

## Related

- `compliance/eu-ai-act-code-of-practice-2026.md` — the EU binding counterpart
- `issues/nist-ai-rmf-genai-profile-2026.md` — the US voluntary counterpart
- `issues/eu-ai-act-annex-iii-2026.md` — the high-risk classification that triggers the AI Act

## Source URLs (verified 2026-08-10)

- https://standards.iteh.ai/catalog/standards/cen/adc675e8-4669-4965-b4c1-c8f724832217/en-iso-iec-42001-2026
- https://www.tcsa.in/resources/iso-42001-certification-guide-2026
- https://bidda.com/insights/iso-iec-42001-ai-management-system-2026
- https://www.iso.org/standard/42001
- https://www.knowlee.ai/blog/iso-42001-checklist-ai-management
