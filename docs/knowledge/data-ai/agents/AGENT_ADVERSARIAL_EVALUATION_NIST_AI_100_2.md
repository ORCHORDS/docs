# Adversarial Evaluation of Agents with NIST AI 100-2

## Scope

Adversarial evaluation asks how an agent behaves when inputs, retrieved content, tools, or surrounding services are intentionally manipulated. NIST AI 100-2 provides terminology for adversarial machine learning across predictive and generative AI. It is a basis for test design, not a certification scheme. For agents, testing must cover the composed system: a model can resist a prompt while an orchestrator still authorizes a dangerous tool call.

The evaluation boundary includes user instructions, system instructions, retrieval sources, memory, tool descriptions and responses, parsers, policy checks, human approval, and side effects. Separate attacks on confidentiality, integrity, and availability. Also distinguish model-level behavior from application-level failures so remediation is assigned to the correct component.

## Implementation workflow

Build a threat-informed test matrix. Identify attacker access: black-box user, authenticated tenant, malicious document author, compromised tool, insider, or dependency supplier. For each role, list objectives and feasible influence channels. Map cases to NIST terminology where applicable, such as evasion, poisoning, privacy attacks, or misuse, while retaining agent-specific details such as indirect instruction injection and tool-result manipulation.

Define an invariant before writing each test. Examples include “retrieved text cannot change authorization,” “a tool may act only on the approved account,” and “untrusted output never enters a command interpreter without validation.” Specify setup, attack input, expected safe behavior, observable signals, and cleanup. Use benign canaries rather than real secrets or destructive targets.

Execute tests at layers. Unit tests exercise parsers, allowlists, schema validators, and policy decisions. Component tests replace retrieval and tool endpoints with controlled malicious doubles. End-to-end tests run in isolated accounts with reversible side effects. Adaptive testing should vary encoding, placement, language, multi-turn timing, and combinations of otherwise harmless instructions. Keep a fixed regression suite alongside exploratory red-team work.

## Controls

Label trust provenance for every context segment and do not treat content as authority. Make authorization depend on authenticated identity, policy, and validated parameters rather than generated explanations. Constrain tool schemas, destination hosts, file paths, and resource identifiers. Require confirmation for consequential actions and render exactly what will happen, not an agent-generated euphemism.

Prevent poisoned retrieval by controlling ingestion identities, preserving source metadata, scanning changes, and supporting rapid source withdrawal. Isolate evaluation credentials and prohibit production data in adversarial corpora unless formally approved. Rate-limit expensive loops and cap tool calls, tokens, wall time, and fan-out so availability tests cannot become incidents.

## Validation evidence

Store the taxonomy tag, tested build, model/configuration identifier, policy version, seed where available, attack transcript with secrets removed, tool-call record, and expected versus observed result. Report attack success rate with confidence intervals when sampling is involved, but also retain severity-weighted individual failures. A low average must not conceal one path to irreversible action.

Demonstrate that failed attacks produce denials or safe degradation, security telemetry, and no unauthorized side effect. Re-run fixed cases after changes and test nearby variants to detect brittle patches. Independent reviewers should reproduce high-severity findings from documented setup. Track coverage by attack surface and attacker role, not merely the number of prompts executed.

## Failure handling

If a test crosses a real boundary, stop execution, revoke test credentials, reconcile all side effects, and handle exposed data under incident procedures. Quarantine poisoned fixtures and snapshots. For product failures, disable the affected capability or narrow its permissions until a systemic control is verified. Do not fix only the exact string; identify the violated invariant, repair the enforcement layer, and add variant regression cases.

## Canonical sources

- NIST AI 100-2e2025, *Adversarial Machine Learning*: https://doi.org/10.6028/NIST.AI.100-2e2025
- NIST Trustworthy and Responsible AI Resource Center: https://airc.nist.gov/
- NIST AI Risk Management Framework: https://doi.org/10.6028/NIST.AI.100-1
