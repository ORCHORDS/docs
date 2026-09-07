# ISO/IEC 27045:2024 — Big Data Security and Privacy Governance

## 1. Scope

This card governs the application of ISO/IEC 27045:2024 (Information technology — Big data security and privacy — Guidelines for managing big data risks) to the OrchordsAI knowledge base and analytics pipelines. The card applies to all stages of the big data analytics lifecycle: ingestion, storage, processing, analytics, sharing, and disposal. It also aligns controls with ISO/IEC 27001:2022 (ISMS) and ISO/IEC 27002:2022 (control catalogue), and bridges privacy obligations into ISO/IEC 27701:2019 (PIMS) and ISO/IEC 29100:2011 (privacy framework).

## 2. Normative references

- ISO/IEC 27045:2024 — Big data security and privacy — Guidelines for managing big data risks.
- ISO/IEC 27001:2022 — Information security, cybersecurity and privacy protection — ISMS requirements.
- ISO/IEC 27002:2022 — Information security, cybersecurity and privacy protection — Information security controls.
- ISO/IEC 27701:2019 — Extension to ISO/IEC 27001 for privacy information management — Requirements and guidelines.
- ISO/IEC 29100:2011 — Privacy framework.

## 3. Terms and definitions

- Big data: datasets whose volume, velocity, variety, veracity, or value characteristics exceed the capacity of conventional data processing systems.
- Big data analytics ecosystem: the data sources, ingestion pipelines, storage layers, processing engines, analytics workloads, and consumers that together transform raw data into insight.
- Data provenance: the documented lineage of a dataset, including origin, transformations, owners, and consent state.
- Privacy impact assessment (PIA): structured evaluation of processing operations against privacy principles.
- Data subject: identified or identifiable natural person to whom personal data relates.
- Anonymisation: irreversible removal of identifying elements from a dataset such that re-identification is no longer reasonably possible.
- Pseudonymisation: replacement of identifying elements with surrogate identifiers, reversible only with separate controlled information.

## 4. Big data security objectives

The objectives of ISO/IEC 27045:2024 are to extend the ISO/IEC 27001 risk-management process into the big data analytics ecosystem, identify threat surfaces that emerge from scale and distributed processing, and provide guidance that complements ISO/IEC 27002 control selection. The objectives cover confidentiality, integrity, availability, and the additional concerns of data provenance, anonymisation quality, and analytic-output leakage. They also address consent and lawful basis at the dataset and feature levels, and the resilience of analytics workloads against poisoning and model-extraction attacks.

The objective set is deliberately broader than classical CIA triad concerns. Volume and velocity create distinct confidentiality risks through aggregation: data that is non-sensitive in isolation may become sensitive when combined at scale. Variety introduces schema-evolution risks and re-identification risks through quasi-identifiers. Value-driven reuse of datasets across multiple analytic purposes tests purpose-limitation principles and demands metadata that survives dataset transformation. The standard positions these concerns as first-class security objectives that the ISMS must address through targeted controls rather than as residual risks to be accepted.

## 5. Big data analytics ecosystem controls

Controls are organised by ecosystem layer. Ingestion controls require schema validation, source authentication, and rate limiting at the producer boundary. Storage controls require encryption at rest, separation between raw, normalised, and feature layers, and immutable audit trails. Processing controls require tenant isolation in multi-tenant clusters, controlled use of privileged service accounts, and reproducible build pipelines for analytics workloads. Analytics controls require versioned feature stores, model and prompt registries, and reproducible experiment records. Sharing and disposal controls require contract-bound exports, watermarking where applicable, and certified deletion with proof.

Beyond per-layer controls, ISO/IEC 27045:2024 emphasises cross-layer concerns. Data provenance metadata is propagated from ingestion through to the published analytic artefact, ensuring that every output can be traced to its contributing sources. Quality controls address veracity through statistical profiling, outlier detection, and freshness monitoring at each layer. Cluster-level controls cover key management, node attestation, and the segregation of development, test, and production analytics environments. Workload identity controls ensure that analytics jobs authenticate to upstream sources and downstream sinks using short-lived credentials scoped to the least privilege required.

## 6. Privacy controls mapping (ISO/IEC 27701 and 29100 tie-back)

ISO/IEC 27045:2024 privacy guidance is operationalised through ISO/IEC 27701:2019 PIMS extensions (clauses 6 and 7, plus Annex A controls for PII controllers and processors). Each big data processing activity is registered as a PII processing activity with legal basis, retention, cross-border transfer mechanism, and data-subject rights fulfilment path. ISO/IEC 29100:2011 privacy principles — consent, purpose limitation, collection limitation, data minimisation, use/retention/disclosure limitation, accuracy, openness, individual participation, accountability — are mapped to the corresponding ISO/IEC 27701 controls and traced into dataset metadata. De-identification and pseudonymisation techniques are recorded with residual re-identification risk.

The mapping also addresses privacy at the feature and model layers. Feature engineering steps that introduce or amplify identifying attributes are flagged in the privacy register, and analytic outputs are reviewed for personal data leakage before publication. Data-subject rights requests (access, rectification, erasure, restriction, objection, portability) are translated into feasible operations on the analytics estate, including search across feature stores and trained model artefacts, with response times tracked against ISO/IEC 27701 service-level expectations.

## 7. Compliance and audit posture

Internal audits verify that each big data processing activity has an updated risk treatment, a current PIA, and a documented ISO/IEC 27701 control mapping. External audits (ISO/IEC 27001 surveillance and ISO/IEC 27701 certification) sample the analytics estate for evidence of provenance, retention enforcement, and data-subject rights handling. Nonconformities trigger a corrective-action plan routed through the ISMS, with effectiveness verification at the next management review.

This card is reviewed every 180 days. The next scheduled review is 2027-03-07.
