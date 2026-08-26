# eu-ai-act-gpai-model-provider-obligations

The duties of a **General-Purpose AI Model (GPAI) provider** under Chapter V
of the EU AI Act (Articles 51-56). Distinct from high-risk AI *system*
providers (covered in `eu-ai-act.md` and `ai-act-conformity-assessment.md`).
GPAI model obligations have been **in application since 2 August 2025** for
newly-placed models, and the EU AI Office's enforcement powers switched on
in **August 2026**. Providers of models released before 2 Aug 2025 have
until **2 August 2027** to comply.

A "GPAI model" is one trained with broad data at scale, usable for a wide
range of downstream tasks — e.g., a foundation LLM like GPT-4, Claude,
LLaMA, Mistral. If you host, fine-tune-to-release, or distribute such a
model into the EU market, this applies to you.

## Symptom

- You're a startup fine-tuning an open-weights base model (LLaMA, Mistral,
  Qwen) and releasing the weights publicly — and you've not filed anything
  with the EU.
- The EU AI Office sends a request for your GPAI technical documentation
  and you have none prepared.
- A downstream deployer (a SaaS company using your model) asks for the
  Article 53 "information package" you are legally required to give them,
  and you don't have one.
- Your model crossed 10^25 FLOPs of training compute, which means it is
  now presumed to carry **systemic risk** (Article 51), triggering a
  heavier regime, and nobody flagged it.
- A copyright holder files a complaint that you didn't publish an adequate
  training-data summary (Article 53(1)(d)).

## Root cause

Chapter V of the AI Act imposes four sets of duties on GPAI providers,
escalating sharply if the model has systemic risk. Many teams conflate
"the AI Act" with "high-risk systems" (Annex III) and assume their model
work isn't covered. It almost always is.

The four GPAI baseline duties (Article 53):
1. **Technical documentation** — maintain and provide to the AI Office on
   request (Annex XI).
2. **Downstream-provider information** — give downstream deployers the
   info they need to comply with *their* AI Act obligations (Annex XII).
3. **Copyright policy** — put in place and publish a policy to comply with
   EU copyright law, including the DSM Directive's TDM opt-out (see
   `ai-training-data-copyright-tdm.md`).
4. **Training-data summary** — publish a "sufficiently detailed" public
   summary of the content used for training.

Plus the **systemic-risk regime** (Articles 51, 55) for models trained
above 10^25 FLOPs (or otherwise designated by the Commission): adversarial
testing, serious-incident reporting, cybersecurity protections, energy
benchmarking, and risk assessment/mitigation.

## Gotchas

- **"We just fine-tune" can still make you a provider.** If you fine-tune
  a base model and place the fine-tuned weights on the EU market under
  your brand, you are a GPAI provider for that variant. The original
  provider's filing does not cover you.
- **API access counts as placing on the market.** If EU users can call your
  model via API, you are placing it on the EU market, regardless of where
  the servers sit. Geo-blocking the EU UI is not enough if the API is
  reachable.
- **The 10^25 FLOP threshold is measured cumulatively** across the full
  training run, including any continued-pretraining runs you stack on top
  of a base. Track FLOPs from day one — retrofitting the number is hard.
- **Systemic-risk presumption is rebuttable but the burden is on you.** If
  you can show the model does not in fact pose systemic risk, the
  Commission may agree — but you must affirmatively make that case.
- **Article 53(1)(d) "training data summary" is public.** It is separate
  from the confidential Annex XI technical documentation. You must publish
  a meaningful summary; a one-liner like "we used public web data" is not
  sufficient and invites regulatory follow-up.
- **Downstream providers will ask for Annex XII info even when they're not
  strictly required to.** Treat it as table-stakes for B2B deals.
- **Open-source exemptions are narrow.** The Act permits the AI Office to
  issue guidelines allowing lighter touch for models released under
  open-source licenses, but only for *non-systemic-risk* models and only
  where the license doesn't include compensation. Don't assume
  open-weights = exempt.

## Fix / practical setup

1. **Decide if you are a GPAI provider.** You are if you develop (or
   materially modify and place on the market) a model with broad capability.
   Pure users of an API (who don't redistribute the model) are *deployers*,
   not providers — different (lighter) rules apply.

2. **Maintain Annex XI technical documentation.** A living internal doc
   covering: model architecture, training data composition and
   provenance, training compute (FLOPs), fine-tuning stages, evaluation
   results, red-teaming methodology, and known limitations. Treat it like
   a regulatory dossier — version it, date it, store it outside the
   engineering team's Notion.

3. **Publish a copyright compliance policy** and link to it publicly. It
   should describe how you honour TDM opt-outs and respond to takedown
   requests. This satisfies Article 53(1)(c).

4. **Publish the training-data summary** on a stable URL (e.g.
   `yourcompany.com/ai/training-data-summary`). Include: high-level data
   categories, opt-out filtering method, processing steps, and a contact
   for rights-holder queries.

5. **Prepare the Annex XII downstream-provider package** and send it
   automatically to every B2B customer and every party that downloads the
   weights. Should include: model capabilities/limits, training-data
   categories, evaluation metrics, and any known failure modes relevant
   to high-risk downstream use.

6. **Set up serious-incident reporting** if you cross the systemic-risk
   threshold. Define what counts as a "serious incident" (e.g., model
   output causing harm to fundamental rights, physical safety, or a
   cybersecurity breach of the model itself) and route reports to the AI
   Office without undue delay and within 15 days latest.

7. **Track FLOPs in your training ledger.** A simple `trainings.jsonl`
   with date, run ID, compute provider, FLOPs, and cumulative total. When
   you cross 10^25, automatically flag ops/legal.

8. **Engage with the AI Office Code of Practice.** The Code of Practice
   for GPAI providers is the practical operating standard the Office uses
   to assess compliance. Signing up gives you a defensible "we followed
   the Code" posture and early-warning on enforcement priorities.

## References

- EU AI Act, Chapter V (Articles 51-56): GPAI model rules.
- EU AI Act, Annex XI (technical documentation for GPAI models).
- EU AI Act, Annex XII (information to downstream providers).
- EU AI Office, "Guidelines for Providers of General-Purpose AI Models."
- EU Commission notice on systemic-risk thresholds (10^25 FLOPs).
- See also: `eu-ai-act.md`, `eu-ai-act-code-of-practice-2026.md`,
  `ai-act-conformity-assessment.md`, `ai-training-data-copyright-tdm.md`.
