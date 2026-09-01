# Incident Response for Agent Systems

## Purpose

Agent incidents can combine ordinary cybersecurity compromise with harmful or unauthorized model-mediated behavior. Examples include credential exposure, cross-tenant retrieval, poisoned memory, unauthorized tool effects, instruction manipulation, runaway resource use, and loss of audit evidence. NIST SP 800-61 provides an incident-response foundation, while the NIST AI Risk Management Framework and its Generative AI Profile add AI-specific risk considerations.

An agent incident process should integrate with the organization’s existing security program rather than create an isolated “AI incident” channel. Classification must focus on affected security objectives, people, systems, and business processes. A surprising model response is not automatically an incident, and a valid-looking response can still conceal an unauthorized side effect.

## Preparation workflow

1. Inventory agent services, owners, models, instructions, tools, credentials, retrieval sources, memory stores, policy engines, and downstream targets. Assign on-call and decision authority.
2. Define incident categories and severity using reachable impact. Include confidentiality loss, unauthorized action, integrity corruption, availability or cost exhaustion, safety impact, and evidence impairment.
3. Establish evidence sources: immutable deployment revisions, policy decisions, tool-gateway audit records, model and retrieval metadata, workload identity, traces, content hashes, and resource-side logs.
4. Prepare containment controls that can be applied independently: disable a tool, revoke a credential, block egress, quarantine a corpus, freeze memory writes, route to a safer model configuration, or stop the agent service.
5. Write playbooks for high-impact scenarios and exercise them. Specify who can preserve sensitive prompts, approve shutdown, communicate externally, and restore service.
6. Define post-incident review and regression-test requirements so recovered systems do not return with the same weakness.

## Detection and analysis controls

Correlate the proposed action, authorization decision, executed tool request, and downstream effect. Monitor for impossible tool sequences, unexpected destinations, repeated denied requests, abnormal token or cost consumption, retrieval from unapproved sources, memory changes by unusual identities, and divergence between approved and executed arguments.

Treat user, prompt, response, and retrieved content as potentially sensitive and attacker-controlled. Preserve only what policy allows, with access controls and chain-of-custody metadata. Where full content cannot be retained, store cryptographic hashes, source identifiers, timestamps, and relevant structured facts. A hash can demonstrate equality with later evidence but cannot reconstruct missing context.

Triage should establish scope, affected identities and tenants, first and last known activity, compromised assets, active persistence, and whether the model behavior was causal or merely part of the interface. Check ordinary application and infrastructure compromise before concluding that the event is model-specific.

## Containment, eradication, and recovery

Contain at the narrowest reliable boundary that stops harm. Revoke delegated tokens, suspend affected identities, disable compromised tools, block malicious domains, quarantine poisoned documents and derived indexes, and prevent writes to affected memory. Do not rely on changing the system prompt when the failed control was authorization or sandboxing.

Eradication may require removing malicious source data, rebuilding indexes, replacing compromised images, correcting identity mappings, rotating secrets, and repairing policy. Determine whether derived artifacts or long-term memory carry the contamination forward. Restore from known-good, digest-pinned releases and reviewed data snapshots.

Recover in stages. Begin with read-only or low-impact capabilities, monitor enhanced signals, validate tenant isolation and policy enforcement, then re-enable side effects. Define success criteria and a rollback trigger before restoration.

## Validation and evidence

Tabletop exercises should test notification, evidence access, containment authority, and decisions under missing telemetry. Technical exercises should use synthetic secrets and safe tool targets to confirm that revocation, quarantine, shutdown, and restoration work within required times.

For each incident, preserve a timeline, affected versions and digests, identities, policy revisions, event correlations, containment actions, evidence-handling record, root-cause analysis, recovery validation, and corrective-action owners. Validate the repair with the original scenario plus adjacent variants. Record residual uncertainty; do not state that all exposure was removed when logs or retention gaps prevent that conclusion.

## Failure handling

If telemetry is incomplete, explicitly bound conclusions and use independent sources such as identity-provider, network, cloud-resource, and destination-system logs. If containment would destroy volatile evidence, responders should balance collection against ongoing harm according to preassigned authority; preventing continued high-impact damage takes priority.

If a third-party model, tool, or data service is implicated, preserve request identifiers and contractual notification details, but do not wait for the provider before applying local containment. Escalate legal, privacy, safety, and regulatory notifications through established processes. Reopen the incident if recovery monitoring shows repeated behavior or contaminated state.

## Canonical sources

- NIST, *Computer Security Incident Handling Guide* (SP 800-61 Rev. 2): https://csrc.nist.gov/pubs/sp/800/61/r2/final
- NIST, *AI Risk Management Framework 1.0*: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
- NIST, *Artificial Intelligence Risk Management Framework: Generative Artificial Intelligence Profile* (NIST AI 600-1): https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.600-1.pdf
- NIST, *Cybersecurity Framework 2.0*: https://nvlpubs.nist.gov/nistpubs/CSWP/NIST.CSWP.29.pdf
