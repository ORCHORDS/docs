# Threat Hunting Hypothesis Playbook

## Purpose

Convert threat intelligence into falsifiable hunting hypotheses, run them against operational telemetry, and turn confirmed findings into detection rules and response procedures. Anchors hunting activity in evidence rather than anecdote.

## Procedure

1. Capture a hypothesis in the form "If an adversary is doing X, then telemetry Y will contain signal Z, given coverage C."
2. Identify the required data sources (endpoint, network, identity, cloud, application) and verify the data is available and timely.
3. Define a pass or fail criterion up front: what observation, in what time window, would confirm the hypothesis; what would refute it.
4. Run the hunt, recording every step and its result (query, time range, returned count, sample observations).
5. If confirmed, create a detection rule with the same telemetry source; if refuted, document the negative result so it can be revisited when telemetry improves.
6. If neither confirmed nor refuted due to data gaps, record the gap and add it to the telemetry roadmap.
7. Brief operations and leadership with the outcome (confirmed, refuted, blocked by gap) and route any confirmed finding into the incident response playbook.
8. Repeat the cycle at a regular cadence and on every significant threat intel trigger.

## Source basis

- NIST SP 800-61 Rev. 2 — Computer Security Incident Handling Guide.
- NIST SP 800-86 — Guide to Integrating Forensic Techniques into Incident Response.
- MITRE ATT&CK and MITRE D3FEND for adversary tactic and technique references.
- SANS Threat Hunting model.
