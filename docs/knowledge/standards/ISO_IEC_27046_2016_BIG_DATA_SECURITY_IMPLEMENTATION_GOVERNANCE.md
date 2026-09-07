# ISO/IEC 27046:2016 — Big Data Security and Privacy Implementation Guidelines Governance

## 1. Scope

This card governs the application of ISO/IEC 27046:2016, "Information technology — Big data security and privacy — Implementation guidelines", to the OrchordsAI big data analytics estate. The standard provides a framework of technical and organizational security and privacy controls that complement ISO/IEC 27002:2022 by addressing risks specific to the volume, velocity, variety, veracity, and value characteristics of big data processing. The card applies to ingestion, storage, processing, analytics, sharing, archival, and disposal across batch, streaming, and interactive analytics workloads. It cross-references ISO/IEC 27045:2024 for big data risk management and ISO/IEC 27001 / 27002 for ISMS alignment.

## 2. Normative references

- ISO/IEC 27046:2016 — Big data security and privacy — Implementation guidelines.
- ISO/IEC 27045:2024 — Big data security and privacy — Guidelines for managing big data risks.
- ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — ISMS requirements.
- ISO/IEC 27002:2022 — Information security, cybersecurity and privacy protection — Information security controls.
- ISO/IEC 27701:2019 — Privacy information management extension to ISO/IEC 27001.
- ISO/IEC 29100:2011 — Privacy framework.
- ISO/IEC 20547-3:2020 — Reference architecture for big data — Security and privacy.

## 3. Terms and definitions

- Big data: datasets whose size, complexity, or update velocity exceeds the capacity of conventional database systems to capture, manage, and process within acceptable time horizons.
- Data lake: storage repository that holds raw data in native format until needed for analytics.
- Data provenance: documented lineage of a dataset, including origin, transformations, owners, consent, and retention metadata.
- Anonymisation: irreversible removal of identifying elements such that re-identification is no longer reasonably possible.
- Pseudonymisation: replacement of identifying elements with surrogate identifiers, reversible only with separately controlled information.
- Distributed processing framework: compute paradigm such as MapReduce, Spark, Flink, or stream processors that partitions work across a cluster of nodes.
- Privacy impact assessment (PIA): structured evaluation of a processing activity against privacy principles and legal obligations.

## 4. Big data lifecycle security

ISO/IEC 27046:2016 organises security and privacy implementation across the big data lifecycle. The ingestion phase requires source authentication, schema validation at the producer boundary, line-rate monitoring, and tamper-evident capture to detect poisoning at entry. The storage phase requires encryption at rest, separation of raw, normalised, and feature layers, and immutability of audit records. The processing phase requires tenant isolation, short-lived workload identity, and reproducible pipeline definitions.

The analytics phase introduces risks that are distinctive to big data. Feature stores and model registries require versioned access control, signed artefact integrity checks, and reproducibility metadata. Analytics outputs must be reviewed for personal data leakage, for unauthorized inferences, and for membership-inference disclosure before publication. Sharing and disposal require contract-bound exports, watermarking where appropriate, certified deletion of source datasets, and retention enforcement at the storage layer rather than relying on application-layer deletes alone.

The lifecycle is treated as an end-to-end concern rather than a sequence of independent stages. Cross-cutting controls include provenance propagation, key management, cluster attestation, and segregation of development, test, and production analytics environments. The lifecycle view ensures that a control applied at ingestion remains effective after transformations through storage, processing, and analytics, and that the provenance chain survives into published artefacts.

## 5. Implementation controls and architecture mapping

ISO/IEC 27046:2016 maps implementation guidance to ISO/IEC 27002:2022 Annex A controls while adding big-data-specific controls where Annex A is silent. Confidentiality controls mandate encryption in transit and at rest, separation between tenants, and redaction of sensitive fields before exposing data to lower-trust analytics environments. Integrity controls mandate checksum verification at rest, signed pipeline definitions, reproducible builds for analytics workloads, and write-once audit retention.

Availability controls address the resilience of distributed processing clusters, including quorum policies, node-replacement procedures, and tested failover for streaming pipelines. Authentication and authorization controls address workload identity, short-lived service-account credentials, and attribute-based access control for feature stores and datasets. Network and infrastructure controls enforce segmentation between analytics clusters, sensitive source systems, and consumer-facing services.

Architecture mapping records the placement of each control in the reference architecture: ingestion boundary, distributed storage layer, processing cluster, analytics environment, and consumer integration point. Controls are documented with their threat scenario, the affected lifecycle stages, the responsible owner, and the verification evidence. The architecture mapping is reviewed when new data sources, new processing engines, or new output channels are introduced, and the controls catalog is updated accordingly.

## 6. Privacy and provenance controls

ISO/IEC 27046:2016 extends ISO/IEC 27701:2019 privacy controls into big data processing, with explicit treatment of anonymisation, pseudonymisation, consent tracking, and lawful basis. Each dataset carries provenance metadata describing origin, transformation history, owners, retention rules, and consent or contract terms. The provenance record is signed at each stage of the lifecycle and is itself treated as integrity-sensitive metadata that must be auditable end to end.

Privacy controls are applied at the dataset, feature, and model layers. At the dataset layer, controls enforce lawful basis, retention, and cross-border transfer rules. At the feature layer, controls flag engineered features that amplify identifying attributes and require re-evaluation of the privacy impact. At the model layer, controls address training-data memorisation, output leakage, and the right to explanation for automated decisions. De-identification and pseudonymisation techniques are recorded with the residual re-identification risk and the assumed threat model.

Data subject rights are operationalised over the analytics estate: access requests traverse feature stores and trained model artefacts; rectification and erasure requests trigger re-derivation of affected features or models; portability requests emit exportable bundles with provenance attached. Each right is processed within the service-level expectations of ISO/IEC 27701 and is logged with the data subject identifier, request type, completion timestamp, and any limitations applied.

## 7. Compliance and verification

Verification draws on the ISO/IEC 27001 ISMS audit programme, supplemented by big-data-specific evidence. Internal audits sample processing activities to confirm that risk treatments, PIAs, and provenance metadata are current; that retention rules are enforced at the storage layer; and that data subject rights are honoured against service-level targets. External audits, including ISO/IEC 27001 surveillance and ISO/IEC 27701 certification, sample the same evidence base and may add sector-specific overlays.

Compliance evidence includes policies, control mappings, processing records, technical configurations, and sample-based testing of analytics outputs. Sampling covers routine processing and high-risk activities such as cross-border transfers, automated decision-making, and large-scale profiling. Findings are tracked with severity, root cause, owner, and closure date; repeat findings escalate to executive management review.

Management review includes a dedicated agenda item for the big data analytics estate, covering residual risk, PIA currency, ISO/IEC 27701 control effectiveness, and any changes to architecture, data sources, or model types. Each change is treated as a change event that re-opens the corresponding risk treatment and privacy assessment before production use. The governance records are retained according to the records retention schedule applicable to the underlying data classification.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
