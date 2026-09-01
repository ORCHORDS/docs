# Security Testing Agent Applications with OWASP LLM Guidance

## Purpose

Agent security testing must cover both probabilistic model behavior and deterministic application controls. The OWASP Top 10 for Large Language Model Applications describes recurring risk areas such as prompt injection, sensitive information disclosure, supply-chain weaknesses, data and model poisoning, improper output handling, excessive agency, system prompt leakage, vector and embedding weaknesses, misinformation, and unbounded consumption. OWASP’s Generative AI Security Project also publishes practical guidance for agentic applications.

The lists are risk-awareness resources, not a certification scheme. A test program should map their categories to the specific system architecture and combine them with ordinary application, API, identity, infrastructure, and supply-chain testing.

## Implementation workflow

1. Establish a test scope and architecture inventory. Include model endpoints, system instructions, retrieval ingestion, vector stores, memory, tool registries, credentials, sandboxes, approval interfaces, and output consumers.
2. Translate applicable OWASP risk categories into abuse cases. Name the attacker, entry point, targeted asset, expected control, and observable success or failure condition.
3. Build a versioned test corpus with benign controls, direct attacks, indirect attacks embedded in retrieved or tool-provided data, encoded variants, multilingual variants relevant to supported use, and multi-turn sequences.
4. Run tests in an isolated environment with synthetic identities and non-production targets. Replace destructive tools with instrumented fakes that record attempted effects.
5. Evaluate the entire execution trajectory. A harmless final answer does not compensate for an unauthorized intermediate tool call, data read, or credential disclosure.
6. Classify findings by violated security property and reachable impact. Remediate at the enforcing boundary—parser, policy engine, tool gateway, sandbox, or data pipeline—rather than relying only on prompt wording.
7. Add confirmed findings and safe variants to regression suites and rerun after changes to models, instructions, tools, retrieval corpora, or policy.

## Controls

Separate model output from executable instructions. Validate and encode output for its destination, whether SQL, HTML, shell, URL, or structured tool input. Enforce tool allowlists, argument schemas, resource authorization, rate limits, and side-effect confirmation outside the model. Limit retrieval sources and retain provenance so suspicious content can be traced.

Use synthetic secrets and canary values to test leakage. Never seed a third-party model or shared environment with real credentials for testing. Apply egress controls so a successful injection cannot transmit data to arbitrary endpoints. Bound requests by token, time, cost, recursion depth, and tool-call count to test unbounded-consumption defenses safely.

Protect the test corpus because it may contain bypass techniques. Restrict production red-team activity, define stop conditions, notify operators, and avoid tests that could affect other tenants. Automated model graders may help triage but should not be the sole oracle for authorization or data-exposure findings.

## Validation and evidence

Define pass criteria before execution. Examples include: no tool call without authorization; no cross-tenant retrieval; no secret canary in output or outbound requests; invalid structured output rejected; destructive request held for approval; and budget exhaustion ending with a controlled error. Track both attack success and benign task completion to reveal controls that simply disable functionality.

Repeat stochastic cases enough to estimate observed failure frequency under a fixed configuration, reporting sample size and conditions rather than universal claims. Manually review high-impact traces. Preserve test-case IDs, system and model versions, policy revision, corpus revision, randomization settings when available, complete tool trajectory, deterministic control decisions, and sanitized outputs.

Evidence should include category-to-control mapping, scope, environment isolation, test results, finding severity rationale, remediation change, and regression result. A vendor filter response alone is not evidence that downstream tool authorization worked.

## Failure handling

If testing triggers a real side effect, stop the campaign, invoke the incident process, preserve evidence, and revoke any exposed synthetic or real credential. If a canary appears outside the expected boundary, determine the propagation path before resuming. Quarantine poisoned retrieval items and rebuild affected indexes from reviewed sources.

Treat flaky failures as security findings until bounded analysis explains them. Do not discard a successful exploit merely because it is hard to reproduce. Conversely, distinguish infrastructure errors from blocked attacks. When a model or dependency update causes regressions, restore the last accepted configuration or disable the affected capability while controls are repaired.

## Canonical sources

- OWASP, *Top 10 for Large Language Model Applications*: https://genai.owasp.org/llm-top-10/
- OWASP, *GenAI Security Project*: https://genai.owasp.org/
- OWASP, *Agentic Security Initiative*: https://genai.owasp.org/initiatives/agentic-security-initiative/
- OWASP, *Web Security Testing Guide*: https://owasp.org/www-project-web-security-testing-guide/
- NIST, *Secure Software Development Framework* (SP 800-218): https://csrc.nist.gov/pubs/sp/800/218/final
