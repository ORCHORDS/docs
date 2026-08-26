# ai-copyright-training-data-2026

**Issue:** A team trains a fine-tuned model on scraped web content. A rightsholder sends a DMCA takedown. The team doesn't know what was trained on, what was filtered, or how to remove specific items.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Foundation model training data is largely opaque. Rightsholders are increasingly filing DMCA notices and EU copyright claims against AI providers. The 2023 New York Times lawsuit, the 2024 Authors Guild cases, and the 2025 EU AI Act training-data transparency requirements have made data lineage a compliance concern, not just a research nicety.

## Root cause

Copyright on training data is governed by a patchwork of doctrines: fair use (US), text-and-data mining exception (EU, with opt-outs), commercial vs. non-commercial use, and the rightsholder's explicit opt-out signals (robots.txt, AI-specific opt-out headers). The legal landscape is in flux; a 2026 team that ignores training-data provenance is exposed.

## The five risk areas

1. **Foundation model pre-training data.** A team that uses a vendor model inherits the vendor's training data. The vendor's licensing is the vendor's problem; but downstream liability for outputs may flow to the deployer.
2. **Fine-tuning data.** A team that fine-tunes on customer documents, scraped content, or third-party datasets owns the licensing obligation. Document the source, the license, and the rightsholder permission.
3. **RAG retrieval corpus.** A team that ingests copyrighted documents into a RAG system must have a license for the retrieval corpus. The model's output is not "fair use" because the input was unlicensed.
4. **User-generated content.** A team that allows user prompts and outputs to flow back into training ("train on user data") must disclose this and obtain consent. Many jurisdictions require explicit opt-in.
5. **Generated outputs.** Outputs that closely resemble training data (memorization) can be copyright infringement of the input. A team that publishes a model must mitigate memorization.

## The opt-out signals (2026 standard)

A team ingesting web content must respect these opt-outs:

- **robots.txt** with `User-agent: GPTBot` or `User-agent: *` blocking — most major crawlers respect this
- **AI-specific opt-out headers** (TDMRep, ai.txt, llms.txt) — emerging 2025-2026 standard
- **Rightsholder opt-out lists** (e.g., "Do Not Train" registries, publisher coalition lists)
- **Explicit contractual exclusion** (paywalled content, license-restricted APIs)

A team that ignores these signals and ingests the content anyway is exposed to takedown notices, lawsuits, and reputation damage.

## The EU AI Act training data transparency

Article 53 of the EU AI Act requires providers of general-purpose AI (GPAI) models to:

- Put in place a policy to comply with EU copyright law
- Implement the TDM opt-out reservation under Article 4(3) of the Copyright in the Digital Single Market Directive 2019/790 (i.e., respect rightsholder opt-outs for text-and-data mining)
- Draw up and make publicly available a sufficiently detailed summary of the training data used

The "sufficiently detailed summary" is the new requirement. A vague "trained on web data" is no longer enough. A team building a GPAI model in scope must disclose data categories, sources, and proportions.

## The data lineage minimum

For any AI training or fine-tuning, document:

- **Source:** Where the data came from (URL, license, provider)
- **Date:** When it was collected
- **License:** The license terms (CC-BY, proprietary, public domain, etc.)
- **Opt-out status:** Whether opt-out signals were respected
- **Filtering:** What was filtered out (PII, illegal content, low-quality, duplicates)
- **Attribution:** Whether attribution is required and given

This is the data sheet / datasheet for datasets practice, formalized. The data sheet is the audit trail for compliance.

## The output memorization mitigation

Foundation models can memorize and reproduce training data verbatim. The mitigation pattern:

- **Test for memorization** — prompt the model with the first 50 tokens of a known training text; check if the model continues verbatim
- **Filter outputs** — block outputs that exceed similarity thresholds against known training data (e.g., >90% match for >100 tokens)
- **Differential privacy** during training (DP-SGD) — mathematically bounds memorization
- **Output filtering at the API layer** — runtime check for known copyrighted sequences

A team that publishes a model without testing for memorization is exposed to claims that the model's output infringes copyright.

## The US fair use vs EU TDM exception

| Jurisdiction | Default | Rightsholder override | Burden of proof |
|---|---|---|---|
| US fair use | Use is presumptively fair | Rightsholder must litigate | Rightsholder proves market harm, transformativeness, etc. |
| EU TDM exception | TDM allowed for research; commercial requires rightsholder permission | Rightsholder can opt out via machine-readable means | Provider must respect opt-out |
| Japan | TDM allowed broadly | Limited opt-out | Rightsholder must show specific harm |
| UK | TDM allowed for non-commercial; commercial needs license | Rightsholder can opt out | Provider must respect opt-out |

A team operating in the EU must respect the TDM opt-out. A team operating in the US has more leeway but faces active litigation.

## The five-step compliance pattern

1. **Audit training data sources.** Categorize by license, opt-out status, geographic origin.
2. **Respect opt-out signals.** robots.txt, AI-specific headers, registry opt-outs.
3. **Document the lineage.** Data sheet for every dataset, including fine-tuning.
4. **Filter outputs for memorization.** Test for verbatim reproduction; block at the API layer.
5. **Maintain a takedown response process.** Rightsholder submits a notice; team removes the specific item and re-trains or fine-tunes as required.

## Verification

The tell that copyright discipline is working:

- A data sheet exists for every training, fine-tuning, and RAG corpus
- robots.txt and AI-specific opt-out signals are respected
- A takedown response process exists with named owners and SLAs
- Output filtering blocks verbatim reproduction
- The team can answer "what was this model trained on?" for any production model

The tell it isn't:

- "We trained on the open web" is the only documentation
- A rightsholder complaint results in an all-hands scramble
- Output filtering is absent; users report verbatim news articles or book excerpts
- The team has no idea which version of which dataset was used

## Gotchas

- **"Open web" is not a license.** "We scraped the open web" without respecting robots.txt and AI opt-outs is a copyright risk.
- **The model is not a fair use shield.** Even if the model is trained on fair-use material, the output can infringe.
- **Memorization is real.** Without testing and filtering, models can reproduce training data verbatim.
- **The TDM opt-out must be machine-readable.** A rightsholder listing "no AI training" in their terms is not a TDM opt-out. The opt-out must be in robots.txt, ai.txt, or TDMRep.
- **The EU AI Act training data summary is public.** A vague summary is a compliance breach; vague summaries invite scrutiny.
- **The rightsholder opt-out list is growing.** A 2025 publisher coalition list included 80+ major publishers. A team that ignores it is exposed.
- **Fine-tuning inherits upstream licensing.** If the foundation model was trained on unlicensed data, the fine-tune is contaminated. Verify upstream before fine-tuning.

## Related

- `issues/eu-ai-act-annex-iii-2026.md` — high-risk classification
- `lessons/ai-red-teaming-2026.md` — adversarial testing of outputs
- `lessons/ai-bias-fairness-2026.md` — bias and data lineage overlap

## Source URLs (verified 2026-08-10)

- https://artificialintelligenceact.eu/article/53/
- https://eur-lex.europa.eu/legal-content/EN/TXT/?uri=CELEX%3A32019L0790 (Copyright DSM Directive 2019/790)
- https://www.eff.org/issues/ai/copyright
- https://www.govinfo.gov/app/details/GOVPUB-PREX23-PURL-gpo193638
- https://www.freshfields.com/en/our-thinking/blogs/a-fresh-take/the-white-houses-blueprint-for-an-ai-bill-of-rights-the-biden-administration-102i03a
