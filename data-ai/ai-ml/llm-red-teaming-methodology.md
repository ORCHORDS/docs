# llm-red-teaming-methodology

**Issue:** Teams ship LLM features with jailbreak-prevention guardrails bolted on and assume they are covered, but never attack their own system the way an adversary would. Guardrails are defenses; red-teaming is the offensive testing discipline that tells you whether the defenses hold. This article covers how to run structured red-team exercises against your own LLM app — taxonomy, tooling (PyRIT, garak, promptfoo), scoring, and converting findings into regression tests. It is the attack-side complement to the existing prompt-jailbreak-prevention and prompt-injection-attacks articles.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Scope the exercise before attacking

1. **Enumerate the attack surface beyond the chat box.** Every place untrusted text meets the model: system prompt contents, RAG documents (indirect injection), tool outputs (web pages, emails), file uploads, other agents' messages. Most real breaches arrive through retrieved content, not typed user input.
2. **Define "harmful" for YOUR app concretely.** A support bot, a code agent, and a KYC flow have different failure classes: data exfiltration via tool calls, system-prompt extraction, PII leakage, unsafe content, unauthorized actions. Write the list before testing or every finding becomes an argument.
3. **Map to a standard taxonomy.** The OWASP Top 10 for LLM Applications (now folded into the OWASP GenAI Security Project; 2025 list covers prompt injection, sensitive information disclosure, supply chain, excessive agency) plus MITRE ATLAS gives structure, comparability, and compliance-ready reporting. Insurance and enterprise buyers increasingly ask for exactly this mapping.
4. **Include the agents and tools, not just the model.** Excessive agency — the model tricked into calling a tool (send email, write file, run shell) — is the highest-severity class in agentic apps. Test with tool access enabled, exactly as deployed.
5. **Time-box and iterate.** A scheduled red-team hour per release beats an annual pentest; guardrail-vs-attack is a moving equilibrium on both sides.

## Tooling that does the grind

1. **PyRIT (Microsoft).** An LLM-driven attacker agent that mutates prompts across many attack strategies against a target endpoint, plus a scoring engine (static classifiers or LLM judges) that grades responses for harm. Best for automated, multi-turn adversarial conversations at scale.
2. **garak.** A vulnerability scanner with a probe library (prompt injection, data leakage, hallucination, toxicity, decoder exploits) — run `garak` against a model or endpoint and get a findings report. Best breadth-per-minute for first-pass scanning of a new model or config.
3. **promptfoo.** Red-team checks as versioned config alongside your existing eval suite — the natural home for regression tests derived from findings (it doubles as the CI gate).
4. **Attack-technique rotation.** Cover the classics: persona/DAN-style roleplay, many-shot jailbreaks (long prefilled conversations), encoding/cipher obfuscation, translation laundering, gradient-of-politeness escalation, prefix-injection ("Sure, here's how..."), and indirect injection planted in RAG docs and tool output. Automated frameworks implement most of these as strategies.
5. **Manual creativity still finds what scanners miss.** Automated probes find known classes fast; the novel bypass specific to your app's wording, tools, or data usually takes a human reading transcripts. Budget both.

## Scoring, reporting, and closing the loop

1. **Score every response with a rubric, not adjectives.** Binary harmful/benign per defined failure class (with an LLM judge + spot-checked human sample) produces countable, comparable results across runs and models.
2. **Report severity like security, not like QA.** Critical = tool misuse/exfiltration/system-prompt theft; high = policy-verified jailbreaks; medium = partial leakage; low = degraded refusals. Each finding carries the exact transcript, the class (OWASP/ATLAS ID), and the suggested control.
3. **Convert every confirmed finding into a permanent regression test.** The attack transcript goes into the promptfoo/eval suite so the specific bypass — not just the general class — is checked on every prompt, model, or guardrail change.
4. **Fix in layers: prompt hardening, input/output filtering, tool-permission gating.** Prompt-level instructions alone never hold under attack; the durable fix is usually the tool permission (allowlist, confirmation step) or an output filter between model and action.
5. **Re-run the suite on every change of model, prompt, or retrieval corpus.** A model upgrade silently reopens old jailbreaks; the regression suite is the only thing that catches it cheaply.
6. **Keep responsible-disclosure hygiene.** If third parties red-team your hosted app, define scope, rules of engagement, and a disclosure channel in advance; findings contain working exploits and deserve restricted handling.

## Anti-patterns

1. **Red-teaming once before launch and never again** — every model, prompt, or corpus update resets the board; make it a release gate, not a ceremony.
2. **Testing only direct chat input** — indirect injection through RAG docs and tool outputs is the more realistic agentic attack path and the one most apps never test.
3. **Scoring findings by vibe in a meeting** — without a per-class rubric and transcripts, severity arguments replace fixes.
4. **Treating scanner pass as safe** — garak/PyRIT clean means no KNOWN vulnerabilities in tested classes; the app-specific bypass still needs human eyes.
5. **Fixing findings by patching the prompt only** — the same class resurfaces with reworded attacks; close it with tool-level permissions or filters that do not depend on the model obeying instructions.
