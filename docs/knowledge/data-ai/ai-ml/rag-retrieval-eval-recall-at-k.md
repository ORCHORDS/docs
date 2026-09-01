# RAG Retrieval Evaluation Recall at K

Retrieval evaluation answers a narrow question with precision: of the passages that contain the answer, how many did the retriever surface in its top K? Recall@K is the metric that gates everything downstream — a generator cannot use a passage the retriever never delivered — and it is also the metric most often computed on datasets too small, too stale, or too easy to mean anything. Building the golden set honestly is harder than computing the metric on it.

## Scope

This article covers retrieval evaluation methodology for RAG: golden-set construction, relevance judgment standards, recall@K and companion metrics, evaluation cadence, and the failure patterns that make evaluation results untrustworthy. It applies to any team making retriever, chunker, embedding, or fusion changes.

Excluded: generation-quality evaluation (answer faithfulness, usefulness — a downstream discipline), online experimentation (live A/B belongs with product analytics), and ranker-training datasets (different construction economics).

The metric family in one paragraph: recall@K measures coverage (did the needed passages appear in top K?); MRR measures ranking (how high did the first relevant passage land?); nDCG grades ranked relevance when relevance is graded rather than binary. Coverage gates the generator; MRR and nDCG matter once coverage is sufficient. Optimizing MRR with recall broken is rearranging deck chairs.

## Workflow or implementation guidance

1. **Build the golden set from real queries, not invented ones.** Sample actual user queries (or a defensible proxy) across traffic classes: identifier-heavy, paraphrase, multi-hop, cross-language if applicable. Invented "typical" queries encode what the builders already believe retrieval should find, which certifies the status quo. A few hundred well-sampled queries with judgments beat thousands of synthetic ones.
2. **Judge relevance against a written standard, not per-annotator taste.** The standard states: a passage is relevant if it contains information sufficient to answer the judged aspect of the query — not merely topically similar. Annotators see the query and passage, mark relevant/partial/irrelevant, and disagreeing cases go to adjudication. Inter-annotator agreement is measured; below a threshold, the standard is rewritten rather than disagreements averaged away.
3. **Allow multiple relevant passages and multi-aspect queries.** Questions with several valid sources must credit all of them; queries with multiple information needs (common in real traffic) get per-aspect judgments. Single-golden-answer datasets systematically overstate recall and hide diversity failures, because any one relevant passage scores full marks.
4. **Compute the metric suite with confidence intervals.** For each change: recall@K at your operating K and at neighboring Ks, MRR, and nDCG if graded judgments exist. Report bootstrap confidence intervals — differences within the interval are noise, and "improvement" claims below the noise floor are how regressions ship dressed as wins.
5. **Version everything that touches the numbers.** The evaluation result is a function of (golden set revision, relevance standard, chunker version, embedding model, index state, retrieval configuration). Pin and record all of them; an unpinned result cannot be compared to anything. Changes one variable at a time between runs.
6. **Run evaluation on every retrieval-affecting change.** Embedding upgrades, chunker edits, fusion weight changes, index rebuilds — each triggers the harness before promotion, with recall@K regression as a blocking gate. The harness runtime budget matters: keep the golden set small enough that the suite runs in minutes, or it will be skipped under pressure.
7. **Refresh the golden set on a schedule and on drift.** Query mix moves with the product; a stale set evaluates yesterday's problems. Refresh quarterly and on major surface changes, re-judging only what changed where possible, and archive old revisions so historical numbers stay interpretable.

## Controls

- **Golden-set change log.** Every revision records what was added/retired and why; results always cite the revision id.
- **Inter-annotator agreement reporting.** Agreement statistics accompany each annotation batch; adjudication is logged, and the relevance standard is versioned.
- **Blocking gate in the promotion pipeline.** Recall@K regression beyond tolerance blocks retrieval-affecting changes; overrides require a recorded justification.
- **Noise-floor discipline.** Reported deltas carry confidence intervals; changes smaller than the interval are recorded as inconclusive, not improvements.
- **Leakage audit.** Golden queries are excluded from any tuning set used to fit retrieval parameters, and duplicate/near-duplicate queries within the set are flagged so a single duplicated pattern cannot dominate the score.

## Validation evidence

- Metric suite with intervals per candidate configuration, each tagged with the full version tuple.
- Annotation provenance: agreement rates, adjudication counts, annotator instructions revision �� demonstrating the judgments, not just the arithmetic, are trustworthy.
- Sensitivity analysis: recall@K across K values and across query classes, showing where the configuration is strong and where it fails (which drives the next iteration, not just pass/fail).
- Trend history: metric over time joined to change records, evidencing that the gate actually operated — including at least one blocked change if history is long enough.

## Failure modes and correction

- **Status-quo certification.** Queries invented by the team match the current chunking and vocabulary; every system scores well and the evaluation detects nothing. Correction: sample real queries; audit the set for phrases that appear verbatim in target documents.
- **Single-golden inflation.** One designated passage per query makes recall look excellent while the system surfaces the same narrow source repeatedly. Correction: multi-relevant judgments per an explicit standard; report coverage diversity alongside recall.
- **Noise-floor gaming.** A 0.8-point recall "gain" inside a ±3-point confidence interval ships as a win. Correction: interval reporting is mandatory; promotion gates compare against the interval, not the point estimate.
- **Stale-set blindness.** The set still reflects last year's product surfaces; a regression on new traffic types is invisible. Correction: scheduled refresh plus drift-triggered refresh with re-judgment of affected classes.
- **Tuned-to-the-test drift.** Repeated weight tuning against the same golden set overfits it; production behavior diverges from scores. Correction: hold out a tuning-free split for final reporting; rotate the tuning split periodically.

## Limitations

Golden-set evaluation approximates production at whatever fidelity the sampling and judgments achieve; long-tail queries and adversarial inputs remain underrepresented by construction. Recall@K on static sets cannot capture freshness effects (index lag behind content changes) or latency-conditioned behavior under load — those need online measurement. Relevance judgment is ultimately human and contestable at the margins; the written standard reduces but does not eliminate subjectivity. Evaluation cost bounds set size; where annotation is expensive, reduced coverage trades against statistical power, and the intervals should honestly reflect that.

## Canonical sources

- BEIR benchmark repository, retrieval evaluation methodology: https://github.com/beir-cellar/beir
- Ranx documentation, Retrieval Evaluation Metrics: https://ranx.readthedocs.io/en/latest/documents/metrics.html
