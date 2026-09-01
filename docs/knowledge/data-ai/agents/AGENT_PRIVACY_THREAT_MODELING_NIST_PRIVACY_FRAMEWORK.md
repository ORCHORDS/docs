# Privacy Threat Modeling for Agent Systems with the NIST Privacy Framework

## Scope

An agent creates privacy risk when it observes conversations, retrieves records, calls tools, and retains intermediate results. This article applies the NIST Privacy Framework to the engineering lifecycle of an agent. It is narrower than general data minimization: the goal is to identify problematic data actions, connect them to affected people, and make privacy risk an explicit design input. The framework is voluntary and outcome based; using it does not by itself establish legal compliance.

Model the full data path rather than only the model request. Inputs can include user text, identity claims, retrieved documents, tool parameters, telemetry, human-review queues, and durable memory. Outputs can expose inferred attributes even when original fields were not retained. The system boundary therefore includes orchestrators, model endpoints, vector stores, policy services, tool providers, logs, evaluators, and support workflows.

## Implementation workflow

Start with an inventory of data processing activities. For each agent capability, record data elements, source, purpose, recipient, retention, jurisdiction, and whether the action is observable or controllable by the person. Map transfers between components and mark where data is transformed, inferred, joined, cached, or exported. Treat tool calls as disclosures when their arguments contain personal data.

Use the Privacy Framework Core functions—Identify-P, Govern-P, Control-P, Communicate-P, and Protect-P—to organize outcomes. Under Identify-P, document contextual factors and affected populations. Under Govern-P, assign owners, risk tolerances, and review triggers. Under Control-P, define choices such as memory opt-in, correction, deletion, and session boundaries. Under Communicate-P, align notices with actual behavior. Under Protect-P, select access, isolation, and data-security safeguards.

Create misuse and error scenarios tied to concrete data actions: an agent retrieves another tenant's record; a summarizer infers health status; a support trace captures credentials; deletion removes the memory index but not the source object; a delegated tool receives more context than required. Estimate likelihood and impact separately, including loss of autonomy, discrimination, embarrassment, economic harm, or chilling effects—not only confidentiality breach impact.

## Controls

Bind each capability to declared purposes and permitted data classes. Enforce tenant and subject filters before retrieval, not after generation. Redact or tokenize sensitive fields before telemetry export. Place expiration on prompts, tool results, embeddings, and review artifacts independently because they may have different stores. Propagate deletion through derived indexes and caches, while retaining only narrowly justified audit evidence.

Require explicit user action before durable memory writes involving personal data. Give reviewers the minimum context needed and prevent copied review data from becoming an unmanaged shadow record. Verify processors and tool endpoints against the inventory before activation. Changes that add a data source, inference, recipient, or retention purpose should trigger privacy review.

## Validation evidence

Maintain a versioned data-flow diagram, processing inventory, risk register, control-to-outcome mapping, and decisions accepting residual risk. Test with synthetic identities across tenants and roles. Evidence should show denied cross-boundary retrieval, successful correction and deletion across replicas, expiry of transient artifacts, telemetry redaction, and notices matching observed network flows.

Run periodic subject-centered walkthroughs: can a person discover what is retained, disable optional memory, correct a wrong attribute, and obtain deletion without hidden copies remaining? Record test IDs, timestamps, storage locations inspected, and exceptions. Privacy metrics should report unresolved deletion failures, unregistered data flows, sensitive-field leakage, and time to remediate—not a single misleading compliance score.

## Failure handling

On unexpected personal-data exposure, stop the affected workflow, preserve access evidence without duplicating sensitive payloads, revoke links or delegated credentials, and identify every recipient and derivative store. Quarantine contaminated evaluation sets and memories. Follow the organization's incident and notification process, then update the data map and threat scenarios. If deletion cannot be proven, report that limitation explicitly and block reuse of the affected store until reconciled.

## Canonical sources

- NIST, Privacy Framework: https://www.nist.gov/privacy-framework
- NIST Privacy Framework 1.0: https://www.nist.gov/system/files/documents/2020/01/16/NIST%20Privacy%20Framework_V1.0.pdf
- NISTIR 8062, *An Introduction to Privacy Engineering and Risk Management in Federal Systems*: https://doi.org/10.6028/NIST.IR.8062
