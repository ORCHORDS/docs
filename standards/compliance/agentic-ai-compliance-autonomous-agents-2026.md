# agentic-ai-compliance-autonomous-agents-2026

- **Issue**: AI agents — LLMs that take actions via tool calls, MCP servers,
  computer use, or payments — are shipping faster than compliance is being
  bolted on. Autonomy creates no exemption: every existing regime (GDPR, EU
  AI Act, state AI laws, PSD2 when money moves) still applies, plus new
  failure modes (unlogged actions, credential sprawl, unauthorized
  consequential decisions). This file is the *compliance* layer;
  `documentation/categories/security/ai-agent-security.md` carries technical controls.
- **Date**: 2026-08-13
- **Repo**: example-org/example-repo
- **Author**: kb-batch-3-compliance
- **Status**: Active. Directly relevant to this repo's own fleet/hooks/MCP
  stack — practice what it preaches here.

## Why agents break existing compliance assumptions

- **The model became an actor.** Compliance regimes assume humans act and
  software records. Agents act and often record nothing by default.
- **GDPR Art. 22 (automated decision-making)**: an agent whose output
  produces legal or similarly significant effects (pricing, hiring support,
  service denial) without meaningful human review needs a lawful basis +
  safeguards. "The user watched a progress bar" is not human review.
- **Accountability (Art. 5(2))**: you must be able to *demonstrate* what the
  agent did, on what data, with what instructions. No logs = no defence.
- **EU AI Act**: agents interacting with humans must disclose they are AI
  (Art. 50, live 2 Aug 2026). GPAI Code safety frameworks explicitly cover
  agentic misuse for systemic-risk models.
- **US**: Colorado's deployer duties and Texas TRAIGA's "deceptive AI"
  prohibitions apply to agent behaviour, not just model cards.

## Symptom

- An agent with a company credit card and shell access runs nightly. When a
  customer asks "why did your agent email my clients," the only evidence is
  a token count in a vendor dashboard. Nobody can reconstruct the run.
- A support agent is granted the whole CRM API "for flexibility" —
  data-minimization and purpose-limitation are gone the moment the tool
  schema loads.
- Users chat with the agent for months without disclosure; transcripts are
  retained indefinitely and piped to a US model endpoint with no DPA, no
  retention cap, no Art. 13 notice.
- Two agents were given the same task and raced to book the same resource —
  nobody designed for concurrency, and now there is a duplicate contractual
  commitment.

## Gotchas

- **Disclosure is already due.** Chatbot-style agents must say they're AI in
  EU-facing contexts (Art. 50). Burying it in a terms page is not
  "clear and obvious."
- **Tool scope = data minimization.** Every field in a tool schema is data
  the agent can access and exfiltrate into prompts, logs, and vendor
  endpoints. Scope credentials per task; ban shared god-keys.
- **Irreversible actions need human gates.** Payments, sends to external
  parties, deletions, and contract-signing should require explicit human
  confirmation unless a documented lawful basis + safeguards exist (Art. 22
  analysis on file).
- **Logs are compliance artifacts, not debug noise.** Capture per-run:
  instructions/version, tools available, calls made with inputs and outputs,
  data categories touched, human approvals. Immutable, retained per policy
  (don't keep chat personal data forever either — define a cap).
- **Prompts are personal-data sinks.** Users paste PII into agent context;
  that flows to model providers. Provider DPAs, EU/adequate endpoints or
  SCCs, and zero-retention API tiers are the baseline stack.
- **Sub-agents inherit nothing automatically.** A spawned sub-agent gets its
  own tool scopes and its own logging duty; fleets without per-agent
  identity make the audit trail unusable.
- **"Agentic" is a design choice in enforcement's eyes.** If you could have
  put a human checkpoint and didn't, that weighs against you in both EU
  (oversight duties) and US (reasonable-care/negligence) analyses.
- **Money-moving agents** may trigger PSD2 strong-customer-authentication
  analysis in the EU: agent-initiated payment is not the customer's SCA.

## Practical example — compliance gate around an agent runtime

```text
AGENT SHIP CHECKLIST (per agent, re-run on material change)
  [ ] Role disclosure in first message (Art. 50 / UT / CA)
  [ ] Tool allowlist reviewed; each tool has data-category tag
  [ ] Credentials: per-agent, least-scope, revocable, expiry <= 90d
  [ ] Human-confirmation list defined (pay/send/delete/sign)
  [ ] Spend + rate caps enforced OUTSIDE the model (hardcoded)
  [ ] Run log: instructions ver + tool calls + IO + approvals
      -> append-only store, 12-month default retention
  [ ] PII: provider DPA signed, endpoint region recorded,
      zero-retention tier on, redaction filter on tool outputs
  [ ] Concurrency: idempotency keys on create/book/pay actions
  [ ] DPIA updated if agent touches personal data (it usually does)
  [ ] Kill switch: documented path to disable agent < 5 minutes
  [ ] For EU consequential decisions: Art. 22 analysis on file
      naming the human reviewer and their effective veto
```

Pair every agent launch with a one-paragraph "agent fact sheet" (purpose,
tools, data categories, human gates, log location) — auditors and your own
incident responders will need it in a hurry.
