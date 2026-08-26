# ai-data-lineage-2026

**Issue:** A team trains a model on production logs. The model is in production. A regulator asks "what data was this model trained on, where did it come from, and was consent given?" The team has no answer. The team also can't reproduce the model because the data version is gone.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

AI data lineage is the family tree of training data: where it came from, how it was transformed, who used it, when. Without it, the team can't reproduce models, debug data issues, or satisfy EU AI Act Article 10 (training data documentation) or EU AI Act Article 12 (input data records).

## Root cause

Data lineage for AI is broader than traditional ETL lineage. It must track:

1. **Source provenance** — collection date, method, owner, legal basis
2. **Transformation history** — every preprocessing step with code version + parameters
3. **Data versioning** — immutable dataset versions with content hashes
4. **Usage tracking** — which models trained on which dataset versions
5. **Retention metadata** — retention policies, deletion schedules, regulatory holds

The 2026 default is OpenLineage + Marquez + MLflow for AI-specific lineage.

## The 5-step compliance pattern (EU AI Act Article 10)

For high-risk AI under EU AI Act Article 10 (effective August 2, 2026 for high-risk providers):

1. **Document source and collection time** of training data
2. **Record each filtering, deduplication, preprocessing step**
3. **Version all datasets** (Git-based or versioned catalog)
4. **Document bias-mitigation measures**
5. **Map which model was trained on which dataset version** (MLflow experiment ↔ dataset)

These 5 are the minimum for high-risk AI Article 10 compliance.

## The 4 measurement patterns

| Pattern | Tool | Use case |
|---|---|---|
| OpenLineage events | OpenLineage + Marquez | ETL + ML pipeline lineage |
| ML experiment lineage | MLflow / Weights & Biases | which model was trained on which data |
| Self-contained | dbt (transformations emit lineage) | SQL transformations |
| Log-based | parse WAL/CDC logs, Kafka streams | actual data movements |

The 2026 default: OpenLineage for ETL + MLflow for experiment tracking. Connect via the model registry.

## The 6-step small-team start

A 4-step plan to start in a quarter.

1. **Pick high-impact pipelines** — the ones that are expensive when wrong (production model training, regulatory reports, exec dashboards)
2. **Set up OpenLineage events** — turn on events in Airflow/Dagster + dbt; mostly configuration
3. **Connect collection and visualization** — events to Marquez or DataHub; graph view shows upstream/downstream
4. **Link ML experiments with dataset versions** — MLflow ties dataset version to experiment
5. **Document Article 10 minimums** — source, transformations, versions, bias measures, model-dataset map
6. **Quarterly review** — drift detection, new pipelines added, decommission old

The 80% automation target within 6 months is realistic.

## The 5 best practices

1. **Start with regulated flows** — financial reporting, PII pipelines, AI training for high-risk models
2. **Automate lineage capture** — manual lineage goes stale immediately; use SQL parsing (dbt, Atlan) + pipeline metadata (Airflow)
3. **Connect lineage to data quality** — freshness, completeness, uniqueness, schema conformance
4. **Extend lineage to ML assets** — track training data, feature definitions, hyperparameters per model version
5. **Treat inference data as a first-class asset** — prompts, outputs, logs; EU AI Act Article 12 requires input data records

## The 5 anti-patterns

1. **Catalog everything simultaneously.** Start with top 10 high-impact datasets; expand quarterly.
2. **Manual lineage documentation.** It goes stale the moment a pipeline changes. Use OpenLineage.
3. **Lineage without quality.** Knowing where data came from but not whether to trust it is half the value.
4. **No version pinning.** Without immutable dataset versions, you can't reproduce or rollback.
5. **No ML extension.** Traditional ETL lineage misses ML features, model versions, AI outputs. Use MLflow for the ML layer.

## The 4 component model of complete lineage

| Component | What | Example |
|---|---|---|
| Source provenance | origin, collection date, method, owner, legal basis | "Scraped 2025-01-15, internal API v2, owned by data-team@example.com, GDPR Art 6(1)(f) basis" |
| Transformation history | preprocessing, feature engineering, augmentation with code version + parameters | "Filter rows where `confidence < 0.8`, commit abc123, params: threshold=0.8" |
| Data versioning | immutable dataset versions with content hashes | "train-v1.2.0 (sha256:abc...), train-v1.3.0 (sha256:def...)" |
| Usage tracking | which models trained on which dataset versions | "model-llm-v2.3 trained on train-v1.2.0 + val-v1.2.0" |

A complete lineage record connects every upstream source to every downstream consumer.

## The 2026 regulatory landscape

| Jurisdiction | Lineage requirement |
|---|---|
| EU AI Act Article 10 | training data documentation for high-risk AI (Aug 2026) |
| EU AI Act Article 12 | input data records for high-risk AI |
| GDPR Article 30 | records of processing activities (general) |
| NIST AI RMF MAP 3.3 | document data provenance |
| ISO/IEC 42001 Annex A | data management controls |
| California AB 2013 | training data disclosure for generative AI |

The 2026 default for any AI team: lineage is a precondition for compliance, not a nice-to-have.

## The 2026 tooling landscape

| Tool | Strength | License |
|---|---|---|
| OpenLineage + Marquez | open standard, vendor-neutral | Apache 2.0 |
| MLflow | ML experiment lineage, model registry | Apache 2.0 |
| Weights & Biases | experiment tracking, model lineage | proprietary + OSS |
| DataHub | metadata platform with lineage | Apache 2.0 |
| Atlan | data catalog with lineage | proprietary |
| OpenMetadata | open metadata + lineage | Apache 2.0 |
| Unity Catalog (Databricks) | lineage across notebooks, jobs, serving | proprietary |
| Marquez (standalone) | open-source lineage server | Apache 2.0 |

The 2026 default stack: OpenLineage + Marquez (lineage) + MLflow (experiments) + DataHub or OpenMetadata (catalog).

## The 5-step implementation pattern

1. **Inventory** — list all datasets, models, training jobs, inference pipelines
2. **Risk-prioritize** — high-risk AI first, then PII, then everything else
3. **Pick 1-2 tools** — OpenLineage + MLflow is the 2026 default
4. **Wire events** — Airflow, dbt, MLflow emit lineage events automatically
5. **Document gaps** — what can't be auto-captured (manual ETL, legacy systems); document manually
6. **Review quarterly** — new pipelines, new datasets, drift in lineage coverage

The first 3 months: 80% lineage for top 10 datasets. Months 4-12: expand to 80% coverage across all.

## Verification

The tell that AI data lineage is real:

- OpenLineage events are emitted from training and inference pipelines
- MLflow links models to dataset versions
- Article 10 documentation is generated from lineage, not assembled manually
- A data quality layer is connected to lineage
- Quarterly lineage coverage review

The tell it isn't:

- "We have a wiki page that lists the data sources"
- No version pinning
- No connection between models and data
- Manual documentation, no automation
- No quality layer

## Gotchas

- **Article 10 is a precondition for high-risk AI market access in EU.** Not optional; not later.
- **Inference data lineage is often missed.** Prompts, outputs, logs are part of the lineage. EU AI Act Article 12 covers this.
- **Inferred data is now "personal information" in Canada (Bill C-36, June 2026).** Document inference; it's regulated.
- **Lineage coverage degrades silently.** New pipelines added without lineage events. Quarterly review is mandatory.
- **The bias-mitigation step is the most-missed documentation.** EU AI Act Article 10 requires it; teams often forget to record which mitigations were applied.

## Related

- `lessons/ai-copyright-training-data-2026.md` — training data provenance
- `issues/eu-ai-act-annex-iii-2026.md` — high-risk AI requirements
- `lessons/ai-rag-patterns-2026.md` — RAG uses lineage for retrieval eval
- `compliance/` — compliance documentation patterns

## Source URLs (verified 2026-08-10)

- https://blog.pebblous.ai/blog/data-lineage-ai-pipeline/en/
- https://underdefense.com/blog/ai-data-governance/
- https://regolo.ai/ai-privacy-and-compliance-in-2026-what-changes-for-llm-providers/
- https://www.glacis.io/guide-ai-data-governance
- https://datarmatics.com/data-governance-ai-guide-2026/
- https://xenoss.io/blog/data-lineage
- https://openlineage.io/ — OpenLineage spec
- https://mlflow.org/ — MLflow
- https://github.com/MarquezProject/marquez
- https://datahubproject.io/ — DataHub
- https://open-metadata.org/ — OpenMetadata
