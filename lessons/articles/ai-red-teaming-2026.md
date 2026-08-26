# ai-red-teaming-2026

**Issue:** A team ships an LLM-powered customer support agent. Three months in, an attacker uses an indirect prompt injection in a customer-uploaded PDF to exfiltrate other customers' data. The team never tested for injection attacks. The incident triggers a regulatory investigation.
**Date:** 2026-08-10
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Symptom

Standard QA processes don't catch prompt injection, jailbreaks, system prompt leakage, hallucination, excessive agency, or supply chain attacks. These failure modes only surface when someone adversarially probes the system. Teams ship without ever running an adversarial test.

## Root cause

LLM applications have a new attack surface that traditional application security testing doesn't cover. The OWASP GenAI LLM Top 10 (published 4 August 2026) catalogs the top 10 vulnerability categories, with five new or substantially revised entries from the 2023 list. The EU AI Act requires adversarial testing for regulated AI systems by August 2026.

Red teaming is the systematic practice of adversarially probing an LLM application to discover security vulnerabilities, safety failures, and factual accuracy issues before deployment. It combines automated attack generation with manual adversarial testing.

## The OWASP GenAI LLM Top 10 (2026)

1. **LLM01: Prompt Injection.** Crafted inputs that override the model's system instructions. Direct injection embeds malicious instructions in user input; indirect injection hides them in external content the model retrieves.
2. **LLM02: Sensitive Information Disclosure.** The model leaks training data, PII, or proprietary information — including system prompt leakage, which was previously a separate category.
3. **LLM03: Supply Chain Vulnerabilities.** Compromised training datasets, poisoned fine-tuning data, or malicious plugins.
4. **LLM04: Data and Model Poisoning.** Manipulation of training or fine-tuning data to alter model behavior.
5. **LLM05: Improper Output Handling.** The application trusts model output without validation, enabling downstream XSS, SSRF, or code injection.
6. **LLM06: Excessive Agency.** The model has access to tools or permissions that exceed what its task requires.
7. **LLM07: System Prompt Leakage.** New in 2025. Attackers extract the system prompt, revealing business logic, guardrail configurations, and internal instructions.
8. **LLM08: Vector and Embedding Weaknesses.** New in 2025. Attacks against RAG pipelines that manipulate the retrieval layer.
9. **LLM09: Misinformation.** The model generates plausible but factually incorrect content (hallucination).
10. **LLM10: Unbounded Consumption.** DoS through excessive resources, recursive reasoning, or infinite tool-calling loops.

The OWASP Top 10 for Agentic Applications (ASI01-ASI10) is the agent-specific successor covering: Agent Goal Hijack, Tool Misuse, Identity and Privilege Abuse, Agentic Supply Chain, Unexpected Code Execution, Memory and Context Poisoning, Insecure Inter-Agent Communication, Cascading Failures, Human-Agent Trust Exploitation, Rogue Agents.

## The four-phase red team loop

A red team program is not a one-time audit. Effective red teaming operates as a continuous loop with four phases:

**Phase 1 — Scope.** Define what to test and what success looks like:

- The application's intended use case and user population
- Which OWASP LLM Top 10 categories apply (all 10 for most applications)
- The model provider and version
- Tools and data sources the model can access
- Acceptable failure thresholds per category

**Phase 2 — Attack.** Run both automated and manual attacks against the scoped categories. Automated tools (DeepTeam, Garak, PyRIT) handle breadth: hundreds of attack variants across known categories. Manual testing handles depth: creative, context-specific attacks automated tools miss.

Key attack patterns:

- Direct prompt injection: "Ignore all previous instructions and..."
- Indirect prompt injection: instructions embedded in retrieved documents or tool outputs
- Jailbreaking: role-play, hypothetical framing, encoding tricks to bypass guardrails
- Tool misuse: tricking the model into calling tools with unintended parameters
- Hallucination probes: ask about entities that don't exist, request statistics for dates after training cutoff, test RAG with poisoned documents

**Phase 3 — Evaluate.** Score each attack result against defined criteria:

- Automated scoring uses classifiers (Llama Guard, OpenAI Moderation API, custom models) to determine if the response violated safety policies
- Manual scoring applies human judgment to edge cases where automated classifiers disagree
- Track catch rate over time; gate releases on catch-rate regression past a threshold

**Phase 4 — Harden.** Fix identified vulnerabilities and re-test:

- Input filtering and prompt sanitization
- Output validation and content filtering
- Reducing model permissions and tool access (addressing excessive agency)
- Adding verification steps for factual claims
- Implementing rate limiting and resource caps
- Updating system prompts with explicit guardrails

After hardening, run the full attack suite again. Mitigations often introduce new failure modes.

## The tools

| Tool | Maintainer | Attack types | Multi-turn | CI/CD | License |
|---|---|---|---|---|---|
| DeepTeam | Confident AI | 50+ attack types | Yes | Yes | MIT |
| Garak | NVIDIA | 100+ probes | Limited | Yes | Apache 2.0 |
| PyRIT | Microsoft | Custom workflows | Yes | Yes | MIT |
| Lakera Gandalf | Lakera | Prompt injection | Yes | Limited | Commercial |

DeepTeam and Garak are the open-source workhorses. PyRIT is for custom red team workflows. Lakera Gandalf is the canonical prompt injection challenge dataset.

## The CI integration pattern

Automated red teaming should run on every PR that touches prompts, model selection, or tool configurations:

```yaml
# .github/workflows/red-team.yml
on:
  pull_request:
    paths:
      - 'prompts/**'
      - 'tools/**'
      - 'models/**'

jobs:
  red-team:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run DeepTeam scan
        run: |
          pip install deepteam
          deepteam scan --category prompt-injection --threshold 0.95
          deepteam scan --category excessive-agency --threshold 1.0
          deepteam scan --category hallucination --threshold 0.90
      - name: Run Garak probes
        run: |
          pip install garak
          garak --model openai --probes promptinject,dan,jailbreak
```

Maintain a corpus of 500-2,000 known prompt-injection attacks across direct, indirect, encoding, role-play, and tool-call categories. Run on every PR. Gate releases on catch-rate regression past a threshold. Add every new disclosed attack pattern to the corpus within 24 hours.

## The hallucination red team

Separate technique, same discipline:

- Ask about entities that don't exist: "Tell me about the Anderson-Whitfield theorem in quantum computing"
- Request statistics for dates after the training cutoff
- Ask questions where the correct answer is "I don't know" and measure refusal rates
- Present contradictory evidence; check whether the model revises or doubles down
- Test RAG with deliberately poisoned documents

Track refusal rate, leak rate, and guardrail trigger rate on a rolling window. Alarm on drift.

## The 50+ known jailbreak regression set

Maintain a regression suite of 50+ known role-play jailbreaks (Garak's `dan` probe, JailbreakBench). Score the model's response with a "did it comply with the jailbreak" rubric and gate CI on the result. A model that complies with a known jailbreak is a release blocker.

## Verification

The tell that red teaming is working:

- A 500+ attack regression suite runs on every PR; release blocked on catch-rate regression
- New attack patterns added to the corpus within 24 hours of disclosure
- Manual red team exercises run quarterly, plus on any major scope change
- The team can name the OWASP categories most relevant to their application
- Production monitoring tracks refusal rate, leak rate, and guardrail trigger rate

The tell it isn't:

- "We tested it ourselves" with no regression suite
- A corpus that has not been updated since launch
- Quarterly reviews skipped because "we don't have time"

## Gotchas

- **Red teaming is continuous, not one-time.** New attack patterns emerge weekly. A corpus from launch is a year stale.
- **Automated and manual are complementary, not substitutes.** Automated tools give breadth; manual testing gives depth. Neither alone is sufficient.
- **The OWASP LLM Top 10 updates.** The 2026 version added system prompt leakage, vector/embedding weaknesses, and unbounded consumption. A 2023 corpus misses these.
- **Hallucination is a red team target, not just a quality metric.** Probe with deliberately fake entities and contradictory evidence.
- **The 95% catch-rate threshold is a target, not a guarantee.** Some attacks always get through. The defense-in-depth stack is what makes successful attacks non-catastrophic.
- **RAG pipelines introduce new attack surfaces.** Indirect injection in retrieved documents is the highest-impact new attack class.

## Related

- `lessons/prompt-injection-defense-2026.md` — the defense stack
- `lessons/agent-guardrails-2026.md` — runtime guardrails
- `lessons/ai-rollout-strategy-2026.md` — the rollout that incorporates red team findings
- `security/prompt-injection-defense-2026.md` — defense-in-depth

## Source URLs (verified 2026-08-10)

- https://owasp.org/www-project-top-10-for-large-language-model-applications/
- https://webcite.co/blog/llm-red-teaming-playbook-2026/
- https://genai.owasp.org/red-teaming-initiative/
- https://www.straiker.ai/blog/top-6-ai-red-teaming-and-adversarial-testing-tools
- https://genai.owasp.org/resource/ai-security-solutions-landscape-for-ai-and-agentic-red-teaming-q2-2026/
