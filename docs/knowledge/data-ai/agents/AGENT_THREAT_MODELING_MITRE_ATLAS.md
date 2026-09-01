# Threat Modeling Agent Systems with MITRE ATLAS

## Purpose

MITRE ATLAS is a knowledge base of adversary tactics and techniques for systems that use artificial intelligence. It can help teams identify realistic attack paths, communicate threats, and relate controls to observable adversary behavior. For an agent system, ATLAS is most useful when applied to concrete assets and trust boundaries: instructions, model endpoints, retrieval stores, tools, credentials, policy engines, memory, artifacts, and human approval channels.

ATLAS is not a compliance standard and a technique catalog is not a complete threat model. A team still needs architecture-specific analysis, likelihood and impact judgments, and controls drawn from applicable security requirements. Technique coverage should not be presented as proof that attacks are impossible.

## Implementation workflow

1. Diagram the system and data flows. Mark boundaries between users, agent runtime, model service, retrieval system, tool gateway, third-party services, and administrative plane.
2. Inventory assets and security objectives. Include confidentiality of prompts and retrieved data, integrity of instructions and tools, availability budgets, authorization state, audit evidence, and safety of physical or financial effects.
3. Identify entry points and attacker positions. Consider an unauthenticated user, malicious tenant, compromised document source, hostile tool response, dependency maintainer, insider, and compromised runtime workload.
4. Search ATLAS for tactics and techniques relevant to each position and asset. Record the exact technique identifier and description used; do not infer that every catalog item applies.
5. Build attack paths that connect prerequisites, technique steps, affected components, and intended impact. Add non-AI techniques from ATT&CK or another threat method when ordinary credential theft, network intrusion, or supply-chain compromise is part of the path.
6. Assign preventive, detective, and recovery controls to each path. Name the enforcement component and evidence source. Track residual risk and an accountable owner.
7. Convert important paths into tests, monitoring hypotheses, and incident playbooks. Revisit the model after architecture, tool access, data sources, or model behavior changes.

## Controls

Keep trust-boundary enforcement outside model discretion. Validate tool arguments, authorize canonical resources, isolate tenants, limit credentials, sandbox untrusted processing, and require human approval for selected irreversible effects. Treat retrieved text, web pages, tool output, and inter-agent messages as data that may contain adversarial instructions.

Map detections to observable facts rather than to vague labels such as “AI attack.” Examples include a document causing an unexpected tool request, repeated attempts to enumerate system instructions, abnormal tool sequences, retrieval from a newly introduced source, or a model endpoint accessed by an unapproved workload. Ensure telemetry does not expose the sensitive content it is intended to protect.

Document assumptions. If a control relies on a model classifier, state its tested operating conditions and false-negative tolerance. Defense in depth should include deterministic enforcement for permissions and side effects rather than depending solely on probabilistic screening.

## Validation and evidence

For each high-priority path, create a test case with safe fixtures and an expected control outcome. Test instruction injection through user input, retrieved content, and tool output separately because their boundaries differ. Exercise attempts to access another tenant’s data, invoke an unregistered tool, alter a high-impact argument after approval, exhaust resources, and bypass logging.

Measure prevention rate, detection latency, alert fidelity, containment time, and recovery outcome. Red-team exercises should preserve the exact scenario, environment, model and policy versions, prompts or payload hashes where content cannot be retained, tool sequence, and observed decisions. A blocked test demonstrates behavior for that scenario, not universal resistance.

Maintain the architecture diagram, ATLAS mappings, attack-path records, control owners, test results, accepted risks, and remediation tickets as evidence. Record the ATLAS version or access date because the knowledge base evolves.

## Failure handling

When a test bypasses a control, stop or isolate the affected capability if the potential impact is high. Preserve trace and audit evidence, determine which trust boundary failed, and fix the deterministic enforcement point before tuning model prompts. Add the bypass as a regression case and search for related paths sharing the same weakness.

During a suspected attack, revoke exposed credentials, disable compromised data sources or tools, quarantine untrusted memory and artifacts, and restore from known-good configurations as appropriate. Do not erase attacker-supplied content before preserving required forensic evidence. If no ATLAS technique fits, document the behavior directly; catalog coverage must not constrain incident recognition.

## Canonical sources

- MITRE, *Adversarial Threat Landscape for Artificial-Intelligence Systems (ATLAS)*: https://atlas.mitre.org/
- MITRE ATLAS techniques: https://atlas.mitre.org/techniques/
- MITRE ATLAS case studies: https://atlas.mitre.org/studies/
- MITRE ATT&CK, enterprise tactics and techniques: https://attack.mitre.org/
- NIST, *AI Risk Management Framework 1.0*: https://nvlpubs.nist.gov/nistpubs/ai/NIST.AI.100-1.pdf
