# ai-training-data-copyright-tdm

Compliance for using third-party text, images, code, and data as training
corpora for AI/ML models. Covers the EU DSM Directive's Text-and-Data-Mining
(TDM) exception, machine-readable opt-outs (Robots.txt, `CC-MAIN.noindex`,
`NoAI` meta tags), and the licensing stack a 2026 dev team needs to stay
defensible when an author or rights-holder claims their work was scraped
without permission.

## Symptom

You hit one of these:
- A rights-holder (author, publisher, stock-photo agency) sends a takedown or
  cease-and-desist alleging their copyrighted work is in your training set.
- You're about to fine-tune a model on a web-scraped corpus (Common Crawl,
  Reddit dumps, GitHub, HuggingFace dataset) and legal asks "are we allowed
  to train on this?"
- A dataset you pulled from HuggingFace turns out to be a re-upload of
  copyrighted books or articles with no license attached.
- Your model regurgitates long verbatim passages from a known copyrighted
  source, and you have no provenance record for the training data.
- A publisher's `robots.txt` says `CC-MAIN.noindex` / `NoAI` but your
  scraper ignored it.

## Root cause

The EU's TDM exception (DSM Directive Articles 3 and 4) lets you mine text
and data **without** the rightsholder's permission, BUT:
- **Article 3** (no opt-out) applies only to research organisations acting
  for non-commercial scientific research.
- **Article 4** (everyone else, including commercial) is subject to a
  **machine-readable opt-out** — if the rights-holder has expressed a
  reservation in an "appropriate manner" (Robots.txt, TDMRep metadata,
  `NoAI` tags), you must respect it. If you don't, you've lost the exception
  and are in straight copyright infringement.

The US has no comparable TDM carve-out; fair use is the only defence and is
fact-specific (see _Andersen v. Stability AI_, _Tremblay v. OpenAI_). Japan
and Singapore have broader TDM exceptions; the UK is still consulting.

## Gotchas

- **HuggingFace is not a license guarantee.** A dataset uploaded as
  `cc-by-4.0` may contain re-published copyrighted works. You inherit the
  infringement risk, not the uploader. Always trace to the original source
  or use the dataset's `datasheets`/`model-card` provenance fields.
- **The opt-out can be in `robots.txt` OR in HTTP headers OR in the content
  itself** (`<meta name="tdm-reservation" content="1">`). A scraper that
  only checks `robots.txt` will miss in-content reservations and lose the
  Article 4 safe harbour.
- **"We only used Common Crawl" is not a defence.** Common Crawl honours
  `robots.txt` at crawl time, but a site that added a `NoAI` reservation
  after being crawled is still in older snapshots. You must re-filter the
  snapshot against current opt-out signals and log the filter run.
- **Derivative datasets inherit restrictions.** If you fine-tune on
  OpenAI output, Anthropic output, or LLaMA-2 output, you are bound by
  *their* terms of service, which may forbid using outputs to train
  competing models. Check the upstream model's Acceptable Use Policy.
- **Code is copyrighted too.** Scraping GitHub public repos does not
  transfer license rights — the code is still GPL/MIT/Apache/etc., and
  your model reproducing GPL code into a proprietary product can create
  copyleft contamination.
- **Removal after training is hard.** "Unlearning" specific works from a
  trained model is an open research problem. The practical compliance path
  is pre-training filtering + provenance logging, not post-hoc deletion.
- **Model cards must disclose training data sources.** Under the EU AI Act
  (Annex XI for GPAI models), you must publish a "sufficiently detailed
  summary of the content used for training." Vague summaries invite
  regulatory follow-up.

## Fix / practical setup

1. **Build a provenance manifest** for every dataset. For each shard, record:
   - source URL or dataset ID
   - crawl/acquire date
   - license declared at source
   - opt-out signals observed (and a hash of the `robots.txt` / TDMRep you
     checked against)
   - filter-pass boolean
   Store as JSONL alongside the data; sign the manifest.

2. **Run a TDM opt-out filter** before tokenising:
   - Fetch and cache `robots.txt` per domain.
   - Parse HTTP headers for `TDM-Reservation: 1`.
   - Parse HTML `<meta name="tdm-reservation">` and `NoAI` tags.
   - Log every match to an audit table with timestamp + evidence snapshot.
   Tooling: `tdm-reservation-checker` (open source), CC's `NoAI` spec.

3. **Prefer licensed data.** Use sources with clear, broad licenses:
   - Wikipedia (CC-BY-SA), arXiv (often CC-BY), PubMed Central OA subset,
     Common Crawl C4 (filtered), datasets explicitly marked `cc0` or
     `cc-by-4.0` on HuggingFace *with traceable origin*.
   - For books: Project Gutenberg (public domain only), or licensed feeds
     like the Authors' Licensing and Collecting Society or direct
     publisher deals (the OpenAI/Bloomsbury model).

4. **Add a "Training Data" section to your model card** listing:
   - high-level composition (% web, % books, % code, % licensed)
   - opt-out filtering method and date
   - a contact address for rights-holder queries / opt-out requests
   This is now legally expected under EU AI Act Annex XI.

5. **Maintain an opt-out request inbox and response SLA.** A rights-holder
   who asks to be excluded from future training must get a response within
   a reasonable window (30 days is the emerging norm). Document the
   exclusion in the next dataset version.

6. **For US-only operations, get explicit licenses or rely on fair use with
   a documented legal opinion.** Do not assume the EU TDM exception
   protects you if you serve the model in the US.

## References

- EU DSM Directive 2019/790, Articles 3 and 4 (TDM exception).
- EU AI Act, Annex XI (technical documentation for GPAI models, including
  training data summary).
- W3C TDMRep specification (machine-readable TDM reservation).
- Creative Commons "NoAI" and "NoTraining" marks.
