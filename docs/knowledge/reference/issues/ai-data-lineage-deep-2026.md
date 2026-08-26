# ai-data-lineage-deep-2026

**Issue:** A team trains a model on data from 12 sources. The team needs to answer "where did this data come from?" for EU AI Act Article 10 (data governance) compliance. The team reads about data catalogs, data lineage, OpenLineage. The team needs the 2026 reference.

**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 5 lineage components

1. **Source provenance.** Where the data originated. URL, dataset DOI, partner, scraping rules.
2. **Transformation history.** How raw data became training-ready. Cleaning, filtering, deduplication, PII removal.
3. **Data versioning.** Which version of the dataset was used for which model. DVC, lakeFS, Hugging Face datasets versioning.
4. **Usage tracking.** Which models consumed which dataset versions. Model cards reference.
5. **Retention metadata.** How long the dataset is kept, deletion schedules, opt-out handling.

## The 5 lineage tools

1. **OpenLineage + Marquez.** Open standard for metadata. Marquez as reference implementation.
2. **DataHub (LinkedIn).** Open-source metadata platform.
3. **Unity Catalog (Databricks).** Integrated with Databricks Lakehouse.
4. **Apache Atlas.** Hadoop ecosystem metadata.
5. **Hugging Face Datasets versioning.** Git LFS for dataset versions.

## The 5 EU AI Act Article 10 requirements

1. **Data governance and management practices** for training, validation, testing data.
2. **Examination of bias** - bias detection and mitigation.
3. **Data minimization** - only data needed for the purpose.
4. **Data quality criteria** - relevance, representativeness, accuracy.
5. **Provenance documentation** - source, collection date, transformation.

## The 5-step lineage implementation

1. **Inventory data sources** with source URL, license, collection date.
2. **Version the dataset** (DVC, lakeFS, or HF datasets).
3. **Track transformations** (OpenLineage events at each step).
4. **Link datasets to models** in model cards and registry.
5. **Maintain lineage graph** (Marquez, DataHub) for querying.

## The 5 anti-patterns

1. **"Data is from the open web"** without source tracking.
2. **No dataset versioning** - "the same data" used for two different training runs.
3. **Transformation steps undocumented** - cleaning pipelines are black boxes.
4. **No link from model to data** - cannot answer "what was this trained on?"
5. **Retention ignored** - data kept after opt-out, GDPR right-to-erasure violated.

## The 5 best practices

1. **Dataset version per training run** (immutable snapshots).
2. **OpenLineage events** for every transformation step.
3. **Model cards** with explicit dataset references and versions.
4. **Opt-out handling** automated in the pipeline.
5. **Retention policies** enforced via storage lifecycle.

## Verification

The tell that AI data lineage is real:

- Every training run references a specific dataset version
- Source provenance documented for all data
- Transformation pipeline emits OpenLineage events
- Model card links to dataset versions
- Opt-out signals processed within 24h
- Retention policy enforced

The tell it isn't:

- "We used the data from Q2" without version
- No link from model card to data
- Manual spreadsheet tracking lineage
- Unknown data sources

## Gotchas

- OpenLineage adoption is real but Marquez-as-a-service is rare; most teams self-host.
- Dataset versioning at PB scale needs lakeFS or Delta Lake, not git LFS.
- Some training pipelines re-process data each run; capture the resulting dataset hash, not the source.
- Opt-out signals (robots.txt, ai.txt) are at the source; pipeline must check at crawl time.
- EU AI Act Article 10 applies to high-risk AI; GPAI is Article 53 (training data summary).

## Source URLs (verified 2026-08-10)

- https://openlineage.io/
- https://marquezproject.github.io/marquez/
- https://datahubproject.io/
- https://dvc.org/
- https://artificialintelligenceact.eu/article/10/
