# Evaluation Data Provenance for Agent Systems

## Scope

Agent evaluation results are only interpretable when the test data's origin, transformations, permitted use, and relationship to production are known. NIST AI RMF measurement outcomes emphasize documented, repeatable assessment, while the NIST Generative AI Profile discusses data privacy, intellectual property, harmful content, and evaluation concerns. This article applies those principles to provenance and governance of agent evaluation corpora.

The scope includes prompts, multi-turn trajectories, retrieved documents, tool simulators, expected actions, grader rubrics, human labels, adversarial cases, and generated synthetic data. It does not prescribe a universal benchmark. Provenance evidence supports fitness and accountability; it does not guarantee that a dataset represents all deployment conditions.

## Implementation workflow

Create a dataset card or equivalent controlled record for each evaluation set. Record owner, purpose, collection method, source locations, collection dates, licenses or permissions, data classifications, affected populations, annotation process, known limitations, prohibited uses, retention, and deletion obligations. Assign an immutable dataset version and integrity digest to the exact material used in a run.

Track transformations as a lineage graph: filtering, deduplication, redaction, translation, augmentation, synthetic generation, label changes, and train-test partitioning. Preserve code and configuration for deterministic steps. For stochastic generation, retain model/configuration identity, seed where supported, sampling settings, acceptance criteria, and reviewer decisions.

Separate development, tuning, regression, and final holdout sets. Restrict access to holdouts so repeated prompt or policy optimization does not turn them into training data. Search for contamination against available training, retrieval, demonstration, and prior evaluation materials using multiple methods; document coverage and uncertainty because absence is rarely provable.

Design cases around real capability and risk claims. Sample by task, language, user group, tool, consequence, and edge condition relevant to deployment. Weighting must be explicit. Include invalid and adversarial cases, but do not let high-volume easy examples drown out rare severe outcomes.

## Controls

Minimize personal and confidential data. Prefer consented, licensed, public-domain, safely synthetic, or appropriately governed sources. Redact identifiers before annotators and graders receive records. Use contractual and technical restrictions for third-party evaluators, and prevent evaluation records from entering model improvement pipelines unless separately authorized.

Control label changes through review and versioning. Store disagreement rather than forcing false certainty where the rubric is subjective. Blind evaluators to candidate identity when feasible. Generated judges require their own manifest, calibration against human judgments, and protection from instructions embedded in evaluated content.

Establish deletion propagation from source examples through transformed datasets, embeddings, caches, and exported subsets. If removal changes reported results, preserve the old report's provenance but restrict the deleted content and issue a new dataset version.

## Validation evidence

For every evaluation run, retain dataset version and digest, split identifiers, sampling logic, execution manifest, grader versions, raw outcomes under access control, aggregate calculations, uncertainty estimates, and exclusions with reasons. Reproduce a sample of cases from source through final score. Verify that each record has a valid lineage path and permitted-use decision.

Audit for duplicate and near-duplicate leakage across splits, missing licenses, expired retention, direct identifiers, label drift, and subgroup undercoverage. Conduct inter-rater reliability or disagreement analysis where human judgment is used. Report limitations beside results, including synthetic-data dependence, unavailable populations, contamination uncertainty, and changes from prior versions.

## Failure handling

If source rights, consent, or confidentiality are uncertain, quarantine the affected records and stop new runs that depend on them. Recompute results on a cleaned version and identify decisions made from invalid evidence. If a holdout leaks, retire it from final assessment, create a new controlled holdout, and label historical comparisons accordingly.

When lineage is incomplete, do not present the evaluation as reproducible. Preserve the execution artifacts that remain, record the evidence gap, and rebuild from authorized sources. Treat exposed sensitive evaluation data as a privacy or security incident and propagate remediation to annotations, exports, and derived stores.

## Canonical sources

- NIST AI RMF 1.0: https://doi.org/10.6028/NIST.AI.100-1
- NIST AI 600-1, *Generative Artificial Intelligence Profile*: https://doi.org/10.6028/NIST.AI.600-1
- NIST AI RMF Playbook: https://airc.nist.gov/airmf-resources/playbook/
