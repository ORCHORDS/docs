# Goal Drift Detection

## Purpose

Control profile for **OWASP ASI01: Agent Goal Hijack**.

## Control

Compare planned actions and material tool calls with the originating goal at defined checkpoints. Large semantic or policy divergence must pause the run instead of being accepted as normal planning.

## Validation

Exercise gradual drift, abrupt redirection, and legitimate plan changes; verify drift signals are explainable and do not block ordinary decomposition.

## Failure correction

Pause affected workflows, capture the divergent plan, tune the detector or policy boundary with evidence, and rerun the same scenario.

## Limitations

Drift detection is a secondary control, not a substitute for authorization. It does not establish OWASP or ACS certification.

## Canonical sources

- https://genai.owasp.org/resource/owasp-top-10-for-agentic-applications-for-2026/
- https://genai.owasp.org/resource/agent-control-standard-acs/
- https://www.nist.gov/publications/artificial-intelligence-risk-management-framework-generative-artificial-intelligence
