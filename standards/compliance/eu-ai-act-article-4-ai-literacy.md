# eu-ai-act-article-4-ai-literacy

- **Issue**: Article 4 of the EU AI Act — the AI literacy obligation — has
  applied since **2 February 2025**, the earliest deadline in the entire Act.
  It applies to providers AND deployers of ALL AI systems, not just high-risk
  ones. Most teams have never heard of it because it produces no product
  feature and no press coverage. It is the AI Act's equivalent of forgetting
  to file taxes: boring, cheap to do, embarrassing when audited.
- **Date**: 2026-08-13
- **Repo**: example-org/example-repo
- **Author**: kb-batch-3-compliance
- **Status**: Active; in force now (the Digital Omnibus proposes trimming it,
  but as of mid-2026 it remains binding — see
  `digital-omnibus-2026-gdpr-ai-act-reform.md`).

## What Article 4 requires

> Providers and deployers of AI systems shall ensure a sufficient level of
> AI literacy of their staff and other persons operating AI systems on their
> behalf.

- **"AI literacy" (Art. 3(56))**: skills, knowledge and understanding that
  allow informed use of AI systems — including the risks and limitations —
  applied in practice.
- **"Sufficient" is role-proportional**: a prompt engineer, a support agent
  using a chatbot, and an exec approving an AI feature need different depth.
- **Scope**: every AI system you ship (provider) or use (deployer) — coding
  assistants, chatbots, OCR with ML, recommendation features. Not only
  Annex III high-risk systems.
- The Commission published **Living guidelines on AI literacy** (Feb 2025,
  updated since) listing pillars: AI basics, data practices, risk awareness,
  responsible use, organizational context.

## Symptom

- A company has a full Annex III conformity folder for one product — and
  zero records that anyone was trained on using the office chatbot, the
  coding copilot, or the support AI. The high-risk paperwork is compliant;
  Art. 4 is violated daily.
- Staff paste customer personal data into consumer AI tools with no training
  on why that's a GDPR problem — that is a double failure (Art. 4 + GDPR).
- An agency deploys an AI feature built by a vendor and assumes the vendor's
  training covers them. It does not: **deployer** duties are separate.
- Contractors/temp staff operate AI tooling on the company's behalf with no
  onboarding. "Other persons operating on their behalf" includes them.

## Gotchas

- **No de minimis.** One chatbot, one team, one EU-affected user — the duty
  exists. Enforcement is member-state level (market surveillance
  authorities) and mostly complaint-triggered, but employee complaints and
  works councils are realistic triggers.
- **Penalties are real if unharmonized.** Art. 4 sits in the
  general-penalty tier (Art. 99(4)): member states set "effective,
  proportionate and dissuasive" fines, up to €15M or 3% in the AI Act's
  ceiling structure. Several DPAs have listed AI literacy in audit
  questionnaires already.
- **Documentation is the deliverable.** Regulators ask for evidence:
  training curricula, attendance, comprehension checks, refresh cadence.
  "We did a lunch-and-learn once" with no record equals no compliance.
- **The Omnibus may soften it — do not bet the audit.** Draft amendments
  have targeted Art 4 for simplification, but it remains in force through
  mid-2026 negotiations. Continuing costs little; stopping costs an excuse.
- **Literacy ≠ one-time onboarding.** Systems change; refresher training
  when materially new AI features ship is the defensible pattern.
- **Vendors can't outsource your duty** but good ones help: ask model/API
  providers for enablement materials and keep them on file as part of your
  program.
- **Track EU staff usage of AI even for non-EU systems.** Deployers of AI
  systems used in a work context connected to the EU market are the target;
  the safest read is: if your org operates in the EU, train the org.

## Practical example — a lean, auditable program

```markdown
# AI Literacy Program — ACME (deployer)

Roles and depth:
  ALL STAFF (45 min, yearly)
    - what AI systems we use; data-entry rules (no personal data in
      unapproved tools); hallucination basics; escalation path.
  AI FEATURE OWNERS (half-day, on assignment + yearly)
    - intended-purpose discipline; monitoring; incident reporting;
      when a DPIA/FRIA is triggered; logging duties.
  ENGINEERS USING COPILOTS (2h, yearly)
    - license contamination of generated code; secret leakage;
      verification duty before merge; logging of AI-assisted changes.

Evidence pack (kept by DPO, retention 3y):
  - curriculum + slides per tier (versioned)
  - attendance export from HR system (per cohort, per date)
  - 5-question comprehension check results (pass >= 4/5)
  - refresh log: re-run whenever a materially new AI system is deployed
  - contractor clause: staffing agencies attest same training delivered
```

This pairs with `ethics-ai-governance-framework.md` (governance layer) and
`us-state-ai-laws-2026-colorado-texas-california.md` (Colorado imposes its
own duty-of-care on deployers — one program can serve both).
