# ai-agent-testing-2026

**Issue:** Agent ships to production. Real users hit edge cases the unit tests didn't cover. The 70/20/10 pyramid from traditional software doesn't translate — LLM outputs are non-deterministic, and "did the agent work" is a fuzzy judgment.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Traditional test pyramid (70% unit, 20% integration, 10% E2E) rests on three assumptions:

1. Units are cheap to run
2. Units are isolated from external systems
3. Units are deterministic

LLM agents break all three. A "unit" that includes a real LLM call is slow, expensive, and non-deterministic. A test that asserts on exact output text fails on every model temperature > 0. Teams either over-mock (the test passes but production breaks) or over-test-real (the CI costs $2000/run).

## Root cause

Agent behavior is partially nondeterministic. The same input produces different valid outputs depending on context, model state, and prompt history. The test pyramid needs an adaptation that pushes LLM dependency as high as possible and replaces "exact match" with "behavioral outcome."

## The agent testing pyramid (adapted)

```
┌─────────────────────────────────────────────┐
│ Production Monitors │ Synthetic probes, canary, chaos
├─────────────────────────────────────────────┤
│ Behavioral Evals │ "Did the agent achieve the goal?"
├─────────────────────────────────────────────┤
│ Integration Tests │ Tool-call sequences, state transitions
├─────────────────────────────────────────────┤
│ Component Tests │ Parsers, routers, tool wrappers
├─────────────────────────────────────────────┤
│ Unit Tests (LLM-free / mocked) │ Pure logic
└─────────────────────────────────────────────┘
```

By count: roughly 70% unit, 20% integration, 10% E2E. By cost and time, the ratio inverts: unit tests are negligible, integration tests are moderate-cost, E2E evals are the most expensive.

The four additions over the classic pyramid: **production monitors, behavioral evals, chaos testing, and shadow validation**. Each catches a class of failure the layer below misses.

## Layer 1: Unit tests, LLM-free and mocked

The rule: **push LLM dependency as high as possible**. Most agent logic doesn't need a real LLM if the boundaries are designed correctly.

Components to test without a real LLM:

- **Prompt builders** — given user message + memory context, does the rendered prompt contain the right fields in the right structure?
- **Response parsers** — given a raw LLM string, does the parser correctly extract tool calls, JSON payloads, structured fields?
- **Context window managers** — does the trimming/summarization logic preserve the right tokens when context exceeds limit?
- **Tool wrappers** — does the filesystem tool correctly sandbox paths; does the HTTP tool correctly set timeouts?
- **Routing logic** — given a detected intent, does the dispatcher select the right sub-agent?
- **Guardrails** — PII detection, prompt injection detection, content filtering: each is a deterministic classifier with a testable input/output

For the thin layer that does interact with the LLM, use test doubles:

- **Stub** — returns a hardcoded string for any input. Use to test parsing code that wraps LLM output.
- **Spy** — wraps a real (or stub) LLM, records what was sent. Assert on prompt construction.
- **Mock** — asserts on call patterns (e.g., "LLM called exactly once with system prompt containing 'JSON'").
- **Record/replay fixture** — captures real API responses once, replays on subsequent runs (vcrpy, ToolTape).

```python
# conftest.py
@pytest.fixture
def mock_llm():
    return MockLLM(responses={
        "extract_invoice": '{"id": "INV-001", "amount": 100}',
        "route_to_billing": "billing_agent",
    })

def test_invoice_extraction(mock_llm):
    result = agent.extract("Please review INV-001 for $100", llm=mock_llm)
    assert result.invoice_id == "INV-001"
    assert result.amount == 100
```

Unit tests run in milliseconds, cost nothing, and should be the bulk of the test suite by count.

## Layer 2: Integration tests with tool tapes

Integration tests exercise the agent's tool-call sequences and state transitions against recorded fixtures. Two patterns:

- **Tool tapes** — recorded fixtures of tool responses, analogous to HTTP cassettes. The agent runs against a replay of a previous session's tool responses. Fast, deterministic, free.
- **Real LLM + sandboxed tools** — slower, more expensive, catches what tapes miss (the LLM making a tool call the tapes don't cover).

The recommended split: 80% tool-tape integration, 20% real-LLM integration. Tape coverage comes from real production sessions; real-LLM coverage focuses on the 5-10 most common workflows.

What integration tests catch that unit tests don't:

- Tool call → tool execution → result parsing — does the agent correctly parse its own tool call?
- State transitions — does the agent correctly advance through stages of a multi-turn workflow?
- Error recovery — when a tool returns an error, does the agent handle it?
- Schema drift — when a tool's response shape changes, does the agent fail gracefully?

Recommended enumeration: list every meaningful state transition the agent can experience. Write one test per scenario. For a moderately complex agent, this is 20-50 integration tests. For a large multi-agent system, 100+.

## Layer 3: Behavioral evals (E2E)

End-to-end tests for agents answer one question: did the agent accomplish the goal? They should not assert on how the agent got there.

- ❌ "The agent called `search_inventory` then `create_order` then `send_confirmation`"
- ✅ "The order was created and the customer received a confirmation within 30 seconds"

The implementation is a labeled dataset of tasks and expected outcomes, run against a live LLM, with multiple evaluation metrics:

- **Answer relevancy** — does the response address the user's question?
- **Hallucination rate** — does the response contain fabricated facts? (per grounding judge)
- **Task completion** — did the agent achieve the stated goal?
- **Tool error rate** — what fraction of tool calls failed or returned malformed data?
- **Cost per task** — is the cost within budget?
- **Latency p50/p95** — is the response time within SLA?

Sample size: 20-50 cases is the Anthropic-recommended starting point. Below 20, statistical noise dominates. Above 50, evaluation cost starts to bite. Mature systems run 100-500 cases per release candidate.

The CI cadence:

- **Every commit:** unit tests (seconds, free)
- **Every PR:** integration tests + 20-case behavioral eval (minutes, low cost)
- **Nightly:** full 100-500 case behavioral eval (30-60 minutes, moderate cost)
- **Weekly:** adversarial / red-team suite (hours, higher cost)
- **On model change:** complete evaluation suite before switching models

## Layer 4: Production monitors and shadow validation

Production monitors are synthetic probes that exercise critical user journeys in production. They run continuously, measure task completion, latency, and cost, and alert on drift.

Shadow validation runs the candidate on real production traffic with zero user effect. The candidate's output is scored offline; production output is what the user sees. This is the same pattern as the rollout shadow stage; in test architecture, it's the canary.

Chaos testing injects failures into recovery paths: tool timeout, malformed response, LLM 5xx, network partition. The agent's recovery behavior is the test target.

## The "did the agent achieve the goal" discipline

The hardest shift is cultural: stop asserting on exact outputs. Three rules:

1. **Test structural properties and invariants**, not exact text. "Output contains the invoice ID" is a structural test. "Output equals 'INV-001'" is brittle.
2. **Use semantic assertions.** "Response mentions the right invoice ID" is more robust than "Response starts with 'The invoice ID is INV-001'."
3. **Assert on outcomes, not traces.** "The order was created in the database" not "The agent called `create_order` with these arguments."

When a test must verify a specific phrasing (e.g., legal disclaimer, regulatory text), use a literal-match assertion, but keep that to a small fraction of tests.

## The minimum viable test stack

For a team starting on agent testing:

- **Week 1:** pytest with mock LLM fixture, unit tests for all non-LLM components, vcrpy for any tests needing recorded real responses
- **Week 2:** enumerate every state transition, write one integration test per transition using scripted LLM sequences, JSON schema validation for structured outputs
- **Week 3:** DeepEval or Braintrust with 20-50 representative inputs, three metrics (answer relevancy, hallucination, task completion), CI gate as non-blocking initially
- **Week 4:** synthetic probes for top 3-5 critical journeys, shadow mode for next major change, chaos fault injection for critical recovery paths

The most important shift is cultural: **treat prompt changes as deployments, evaluate continuously, and measure recovery time as a first-class metric**.

## Verification

The tell that the test stack is working:

- A prompt change ships only after eval score holds or improves on the golden set
- Recovery time from a tool failure is a tracked metric, not a guess
- A new engineer can add a test for a new workflow in under 30 minutes
- CI cost per PR is bounded (under $5 in LLM API spend)

The tell it isn't:

- "Eval" is a single LLM call the engineer made on their laptop
- Tests assert on exact output text and break on every prompt edit
- A prompt change ships without any automated quality check

## Gotchas

- **Don't assert on exact text.** Assert on outcomes, structural properties, and invariants.
- **Mock the LLM in unit tests, use real LLMs in integration tests, use eval sets in E2E tests.** The mocking strategy changes per layer; one strategy across all layers is wrong.
- **20 cases is a starting point, not a target.** Mature systems need 100+ cases. Below 50, statistical noise dominates.
- **Behavioral evals inherit the human ceiling.** If your two experts agree 75% of the time, your eval can score at most 75% reliably.
- **Synthetic probes are not real users.** They cover known critical paths. They miss the unknown unknowns that real users hit.

## Related

- `patterns/agent-eval-2026.md` — building the eval harness
- `lessons/eval-driven-development-2026.md` — the golden set protocol
- `lessons/agent-self-correction.md` — when the agent catches its own errors
- `lessons/ai-rollout-strategy-2026.md` — the shadow/canary gate uses these tests

## Source URLs (verified 2026-08-10)

- https://zylos.ai/research/2026-05-07-ai-agent-testing-strategies-production-validation/
- https://callsphere.ai/blog/testing-ai-agents-unit-integration-end-to-end-evaluation-strategies-2026
- https://tianpan.co/blog/2026-04-15-agent-test-pyramid-llm-testing
- https://docs.aws.amazon.com/ja_jp/wellarchitected/latest/agentic-ai-lens/agentops06-bp01.md
- https://kevinjztan.medium.com/testing-ai-agents-in-production-unit-tests-evals-and-integration-tests-eb0888fde381
- https://www.aiagentlearn.site/tutorials/ai-agent-testing-guide/
- https://agent.ceo/blog/ai-agent-testing-strategies-cyborgenic
