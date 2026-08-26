# denial-of-wallet-llm-cost-abuse

**Issue:** Denial of wallet (DoW) is an attack class in which the adversary's goal is not to exhaust compute or crash a service but to drain the victim's budget, exploiting the usage-based pricing of LLM APIs, embedding pipelines, and paid SaaS tools. Unlike traditional DoS, every request succeeds from the application's point of view while silently accruing cost, so the attack is invisible to availability monitoring and bounded only by the credit limit on the provider account. Attack vectors include injected instructions that force maximal-token outputs or the most expensive model tier, agent loops that repeatedly invoke paid tools, unbounded retrieval expansion that inflates context windows, and public-facing AI features that let anonymous users trigger metered calls. For any product with agentic workflows, cost abuse must be treated as a security property with the same rigor as authentication and rate limiting.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Attack vectors

1. **Prompt-injection-driven spend escalation.** Malicious content ingested via web pages, documents, or user messages can instruct an agent to emit maximum-length responses, call expensive models, or expand every task into dozens of sub-agent invocations, turning an injection flaw into a financial drain.
2. **Runaway agent loops.** Self-correcting loops that retry failing tool calls, recursively spawn sub-agents, or ping-pong between planner and executor can run for hours on a single poisoned input; each iteration bills tokens and tool calls with no natural stopping point.
3. **Unbounded retrieval and context inflation.** RAG flows that fetch until a token ceiling is reached, embed entire document stores per query, or re-embed unchanged content on every request multiply cost per user interaction by orders of magnitude when an attacker drives query volume.
4. **Anonymous and unauthenticated access to metered endpoints.** Public chat, summarization, or generation features without per-identity quotas let a single scripted client convert the deployment into a free LLM proxy at the operator's expense.
5. **Model-tier and tool escalation.** Routing logic that honors client hints or injected instructions when choosing between cheap and premium models, or between local and paid tools, surrenders pricing control to the attacker.

## Budget guardrails

1. **Hard spending caps at every layer.** Set provider-level budget ceilings for the project and per API key, plus in-app budgets per request, session, user, and tenant, so a single runaway flow trips a kill switch instead of the monthly invoice; enforce the caps in code, not only in dashboards.
2. **Token and output ceilings.** Constrain max output tokens, context window usage, and tool-call counts per agent run; refuse to continue a chain whose accumulated spend exceeds the configured envelope, and terminate rather than degrade silently.
3. **Model-tier policy enforcement.** Select model tier server-side from task classification and budget policy; treat any request-sourced preference for a premium model as untrusted input and ignore it.
4. **Separate budgets for untrusted flows.** Give anonymous, free-tier, and user-triggered agentic flows their own isolated quota and credential pool so abuse cannot crowd out or drain paid internal workloads.
5. **Pre-flight cost estimation.** Estimate the cost of an operation, such as tokens to embed a file or calls to complete a plan, before execution and require confirmation or automatic truncation when the estimate exceeds a threshold.

## Circuit breakers and containment

1. **Loop and retry circuit breakers.** Count consecutive tool calls, retries, and self-invocations per run; open the circuit at a fixed bound, fail the task with a diagnosable error, and require human intervention to reset, ending reasoning spirals that are financial events, not just bugs.
2. **Step and depth limits in agent frameworks.** Cap planning depth, sub-agent fan-out, and total wall-clock time per task, and make the caps non-overridable by prompts or runtime configuration the agent can influence.
3. **Safe-mode degradation.** On anomaly, downgrade to the cheapest model, disable tool use, and answer from cache or static content rather than continuing to spend while alerts fire.
4. **Quarantine for suspect tenants.** Automatically suspend accounts or API keys whose spend curve deviates sharply from their baseline, analogous to fraud holds on payment cards.

## Detection and operations

1. **Per-identity cost telemetry.** Attribute every token, call, and tool invocation to a request ID, user, and feature so dashboards can show unit economics and anomalies can be localized to the exact flow that generated them.
2. **Anomaly alerts on spend rate.** Alert on cost per minute, cost per user, and cost per completed task, with thresholds derived from rolling baselines, so a spike pages an engineer within minutes rather than at invoice time.
3. **Caching and deduplication.** Cache identical prompts, embeddings, and tool results to collapse repeated abuse into a single billed execution; cache hits make naive flood attacks cheap to absorb.
4. **Abuse testing in CI.** Load tests should simulate adversarial patterns, including loop-inducing inputs, maximum-length generations, and high-rate anonymous access, and assert that caps, breakers, and suspensions engage within the expected spend envelope.

## References informing this article

1. **Prompt Security, "Denial of Wallet in AI".** Framing of DoW as a security threat class and agent-specific escalation paths.
2. **Oracle, "Runtime Budget Guardrails for Agentic AI".** Policy, observability, circuit-breaker, and safe-mode patterns for governing agent spend.
3. **AI Agent Defense in Depth Model (AIDDM).** Positioning of DoW as a distinct threat layer tied to unbounded input-to-compute relationships.
4. **PromptMetrics, "5 Silent Killers of AI Agents".** Analysis of endless agent loops as active financial events and circuit-breaker mitigation.
