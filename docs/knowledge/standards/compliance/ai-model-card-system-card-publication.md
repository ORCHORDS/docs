# ai-model-card-system-card-publication

Producing and maintaining the **transparency artifacts** that the EU AI Act,
various US frameworks (NIST AI RMF, California SB 1047 lineage, the Biden
EO 14110), and downstream enterprise procurement increasingly require:
**model cards** (for any AI model), **system cards** (for high-risk or
systemic-risk AI systems), and the technical-documentation dossiers that
sit behind them.

A model card is a structured public document describing what a model is,
how it was trained, how it performs (and where it fails), and how it should
(and should not) be used. It is the AI equivalent of a drug label.

This is distinct from `eu-ai-act-gpai-model-provider-obligations.md` (which
covers the legal duties) — this article is about *authoring and publishing
the artifact itself*.

## Symptom

- An enterprise customer's procurement form requires a link to your model
  card, and you either don't have one or the one you have is 6 months out
  of date.
- A regulator (EU AI Office, FTC, or a state Attorney General) asks for
  your model's transparency documentation and you scramble to assemble
  it from Slack threads and stale wikis.
- A user discovers your model produces biased or unsafe output in a
  specific demographic slice, and you have no published evaluation
  results to point to (or to be held to).
- Your model card lives as a PDF on a marketing page; engineers can't
  update it, and the latest model version shipped without a card update.
- Two models in your product line have inconsistent cards because each
  team wrote theirs ad hoc.

## Root cause

Model cards fail for one of three reasons:
1. **No template** — every team invents the structure, so coverage is
   inconsistent and key sections are missed.
2. **No update trigger** — the card is treated as a one-time launch asset,
   not a living document; it goes stale the moment the model is patched.
3. **No publishing pipeline** — the card is locked in a wiki or PDF that
   customers and regulators can't reliably find or verify.

The fix is to treat model cards like SBOMs: generated from the model's
metadata, versioned with the model, and published to a stable, signed URL.

## Gotchas

- **"Intended use" and "out-of-scope use" are the most important
  sections.** They are what regulators and plaintiffs will cite. Be
  specific: "not intended for credit decisions, hiring, or medical
  diagnosis" beats "use responsibly."
- **Evaluation results must include subgroup breakdowns.** Aggregate
  accuracy hides bias. A card that reports 92% overall accuracy but
  doesn't show the 78% for a specific demographic is a liability —
  and increasingly a regulatory red flag.
- **Cards must match the model version.** A card describing v1.0 that
  ships next to a v1.2 model is misleading and, in the EU, can be a
  standalone transparency violation. Tie card version to model version
  and refuse to deploy without a matching card.
- **Training data description ≠ training data summary.** The EU AI Act
  Annex XI requires a sufficiently detailed summary of training content.
  Vague descriptions like "public internet data" are not sufficient.
  Pair the card with the public training-data summary (see
  `eu-ai-act-gpai-model-provider-obligations.md`).
- **System cards are different and bigger.** A *system card* covers an
  AI product (e.g., a chatbot or a hiring tool), including the model
  plus the UI, guardrails, logging, human oversight, and deployment
  context. Don't ship a model card and call it a system card.
- **Red-teaming and known limitations are mandatory, not optional.**
  Omitting them is a transparency failure. Document the worst-known
  failure modes and the mitigations in place.
- **Cards must be machine-readable too.** Customers and regulators want
  to ingest them. Provide a JSON/Hugging Face Model Card metadata block
  (YAML frontmatter) alongside the human-readable Markdown.
- **Don't over-claim safety.** "This model is unbiased" is an invitation
  for a lawsuit. Use calibrated language: "Evaluated on the XYZ
  benchmark; observed the following disparities."

## Fix / practical setup

1. **Adopt one template org-wide.** Start from the Hugging Face Model Card
   guide or Google's original Model Cards paper (Mitchell et al., 2019),
   and extend with EU AI Act fields. Minimum sections:
   - Model details (name, version, owner, date, license, citation)
   - Intended uses and out-of-scope uses
   - Training data summary (composition, processing, opt-out handling)
   - Evaluation (datasets, metrics, subgroup breakdowns, limitations)
   - Ethical considerations and known failure modes
   - Technical specs (architecture, parameters, compute, framework)
   - Contact and complaints mechanism

2. **Generate the card from the model registry.** Each model in your
   registry (MLflow,Weights & Biases, custom) should have metadata fields
   that map 1:1 to the card sections. A script renders the card Markdown +
   YAML from the registry entry. This is the only sustainable path.

3. **Block deployment without a current card.** Add a CI check: if the
   model artifact's version doesn't match a published card version, the
   deploy fails. Treat it like a missing SBOM.

4. **Publish to a stable, versioned URL.** Example:
   `yourcompany.com/ai/models/<model-slug>/v<version>/card.md` plus
   `.json`. Sign the card (Sigstore, GPG) so customers can verify
   provenance. Don't rely on a Hugging Face repo URL alone — you don't
   control that domain.

5. **For high-risk and systemic-risk systems, produce a system card.**
   The system card layers on top of the model card and adds:
   - risk-management measures (AI Act Article 9)
   - data governance (Article 10)
   - technical documentation (Annex IV)
   - record-keeping and logging (Article 12)
   - transparency to deployers (Article 13)
   - human oversight measures (Article 14)
   - accuracy, robustness, cybersecurity (Article 15)
   This is the document an EU conformity assessment will examine.

6. **Review cards at every model update and at least annually.** Log the
   review in an audit trail (reviewer, date, changes). A card that hasn't
   been reviewed in 18 months is presumptively stale.

7. **Link the card from your model card to the SBOM, the VEX, the
   training-data summary, and the copyright policy.** Regulators and
   customers increasingly expect a *package* of transparency artifacts,
   not a single doc.

## References

- EU AI Act, Annex XI (GPAI technical documentation) and Annex IV
  (high-risk system technical documentation).
- EU AI Act, Article 13 (transparency obligations for high-risk systems).
- NIST AI Risk Management Framework (AI RMF 1.0) — "Inform" function.
- Mitchell et al., "Model Cards for Model Reporting" (FAT* 2019).
- Hugging Face Model Card documentation and metadata schema.
- ISO/IEC 42001:2023 (AI management system standard) documentation
  requirements.
- Related articles: `eu-ai-act-gpai-model-provider-obligations.md`,
  `ai-training-data-copyright-tdm.md`, `ethics-ai-governance-framework.md`,
  `sbom-generation-distribution-cicd.md`.
