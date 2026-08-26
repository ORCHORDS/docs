# agentic-payments-protocols-acp-ap2

**Issue:** AI agents (shopping assistants, autonomous operators, coding agents buying cloud resources) now initiate real card payments, and 2025 produced competing protocols for it: Stripe + OpenAI's Agentic Commerce Protocol (ACP, powering "Buy it in ChatGPT" Instant Checkout), Google Cloud + Coinbase's Agent Payments Protocol (AP2, blockchain-settled), and Coinbase's x402. A payments engineer in 2026 has to pick which rails to expose, keep raw PANs away from the agent process, and preserve a human-approval step so an agent cannot silently spend the user's money. The dir covered classic card/crypto/webhook flows but nothing on agent-initiated commerce.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The 2025-2026 protocol landscape

1. **ACP (Agentic Commerce Protocol).** Open standard co-developed by OpenAI and Stripe, announced Sept-Oct 2025 with the "Buy it in ChatGPT" Instant Checkout launch. Card-rail based: the agent discovers products and builds a cart, but payment is delegated to a wallet (Stripe Link) that the human approves.
2. **AP2 (Agent Payments Protocol).** Announced by Google Cloud and Coinbase in September 2025. Different settlement model: programmable payments over modern blockchains (e.g. Sui), designed to interoperate with A2A (agent-to-agent) and MCP. Spec lives at agentpaymentsprotocol.info and github.com/google-agentic-commerce/AP2.
3. **x402.** Coinbase's HTTP-native payment protocol named after the 402 Payment Required status code — a server (or agent) returns 402 with a price, and the caller pays in USDC to retry. Simplest to implement, crypto-settled, and increasingly used for metered API access between agents.
4. **They are not interchangeable.** ACP targets consumer checkout with cards and existing PSP relationships; AP2/x402 target machine-to-machine settlement with on-chain escrow and programmability. Choose per use case: consumer shopping carts -> ACP; agent-to-agent resource purchases -> x402/AP2.

## ACP integration mechanics

1. **Three specs, not one.** ACP is split into Product Feed (standardized catalog/discovery endpoints), Agentic Checkout (cart creation and checkout driven by the agent), and Delegated Payment (wallet-side approval and tokenized payment). Implement them in that order — discovery without checkout is useless to the agent.
2. **JSONWSP service description.** ACP endpoints are formally described with JSONWSP (a JSON-RPC-like describe/discover model), so an agent can introspect your capabilities at runtime. Serve the description document at a stable URL and keep it in sync with your actual handlers.
3. **The agent never touches the card.** In Delegated Payment the buyer's wallet (e.g. Stripe Link) runs an explicit user-approval flow and hands the agent a scoped token to complete the payment. Never design an "agent checkout" that passes a raw PAN or full CVV through the model's context — that is a PCI scope and prompt-injection disaster.
4. **PSP support exists.** Stripe ships agentic-commerce docs (docs.stripe.com/agentic-commerce/acp) and agentic checkout APIs; Visa, Mastercard, and PayPal announced ACP ecosystem participation. If you are already on Stripe, start with their product-feed export + agentic checkout rather than hand-rolling JSONWSP.

## Trust and confirmation model

1. **Human-in-the-loop approval is the core defense.** Every protocol preserves an explicit user confirmation of intent (ACP's wallet approval screen, AP2's transaction-approval step). Any homegrown agent-payment flow must reproduce this: a signed approval bound to amount, payee, and session — not a chat message that says "yes".
2. **Identity assertion is separate from intent.** AP2 and ACP both distinguish "who is the agent acting for" (identity proofing, the human's verified relationship with merchant/wallet) from "did the human approve this transaction" (intent confirmation). Log both independently so disputes can be adjudicated.
3. **Bind approvals to amounts, not sessions.** An approval token should be single-use and amount/payee-pinned; agents re-initiate for changed carts. This blocks the classic "approve a $5 trial, agent completes a $500 annual plan" escalation.
4. **Assume prompt injection.** The agent browsing your product feed is an untrusted client from your threat model's perspective — validate everything server-side, rate-limit cart mutations, and treat "the agent said the user approved" as worthless without the wallet's cryptographic approval artifact.

## Chargebacks, fraud, and ops concerns

1. **Dispute reason codes are still card rules.** ACP payments settle over card rails, so fraud chargebacks arrive under the same Visa/Mastercard reason codes (see chargeback-representment-workflow.md). Retain the wallet approval artifact and agent session log — that is your representment evidence for "unauthorized" claims.
2. **Velocity and spend limits are yours to enforce.** Neither protocol gives you free risk scoring: set per-agent, per-user, and per-session spend ceilings, and require step-up (human re-confirmation) above thresholds. Mirror the velocity-fraud-checks patterns already in this knowledge base.
3. **Agent traffic needs its own monitoring slice.** Tag agent-initiated transactions (source, agent platform, protocol version) in your analytics and audit log from day one; "conversion lift from ChatGPT traffic" and "fraud rate of agent orders" are both unanswerable without that tag.
4. **Keep a kill switch.** Expose an ops toggle to disable agentic checkout endpoints without a deploy. The protocol specs are still moving (ACP and AP2 both iterated through 2025-2026), and you want to be able to freeze the surface when a spec change or abuse pattern appears.

## Gotchas

1. **Name collision: "AP2" vs "ACP" confusion.** Sales and vendor material routinely mix them up. Stripe's protocol is ACP; Google/Coinbase's is AP2. Verify which one a tool or SDK means before integrating — they share zero code.
2. **Specs are young.** Both repos were still publishing revisions into 2026; pin protocol versions, keep the JSONWSP description authoritative, and write contract tests against the spec fixtures rather than blog examples.
3. **Crypto settlement brings reconciliation baggage.** If you adopt AP2/x402, you inherit on-chain settlement lag, gas-paid retries, and USDC-amount rounding — reconcile against the existing crypto-payments-integration.md and nowpayments playbook rather than pretending it is a card charge.
