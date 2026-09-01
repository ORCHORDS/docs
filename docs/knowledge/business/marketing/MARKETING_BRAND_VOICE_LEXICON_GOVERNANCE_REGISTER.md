# Brand Voice Lexicon Governance Register

## Scope

This control governs the curated vocabulary used in customer-facing marketing copy, including headline terms, value propositions, product names, comparative language, descriptive phrases, and preferred substitutes for words considered off-brand, ambiguous, or unsupported. It applies to advertising copy, landing pages, email subject lines, push notification text, social posts, on-site messaging, sales collateral, partner co-marketing, influencer briefings, automated content generation prompts, and any downstream channel that consumes a published lexicon entry. The lexicon register records each term, its approved definition, its source citation, its current status, the products or audiences it applies to, and the owners authorized to revise it.

The governing reference for terminology work is ISO 704, which frames terminology principles and methods for establishing, describing, and managing terms within a domain. The principle that follows from that work is that a controlled term has a definition tied to a concept, a note on usage, and a clear life cycle; a marketing lexicon that lacks definitions or change history is decorative rather than operational. Adoption of this control does not guarantee regulatory compliance, consistency with sector-specific language rules, or platform approval.

## Workflow or implementation guidance

Building a governed brand voice lexicon proceeds in seven iterative steps.

1. Inventory candidate terms. Pull a working corpus of terms from active campaigns, brand guidelines, previous rulings, banned-word lists, and category descriptors that recur in customer service or sales calls. Each candidate term is paired with its current intended meaning, the audiences it appears in front of, and any existing internal definitions.
2. Define each term. Draft a definition that names the concept, sets boundaries, and excludes adjacent meanings. Where ISO 704 style entry structures apply, record the entry as term, definition, context, examples, and any notes about misuse. Avoid circular definitions such as redefining "trusted" as "trustworthy."
3. Cite the source. For every entry, identify where the term comes from: a published brand charter, an internal product specification, an external standard, a regulator's glossary, a court or agency settlement, a competitor's restricted marks list, or an evidence-backed marketing claim.
4. Validate cross-functionally. Have marketing, legal, localization, accessibility, and the product owner review each entry. Flag conflict between terms that overlap or contradict each other, and between this lexicon and adjacent lexicons such as accessibility style guides or regulatory word lists.
5. Publish in a versioned register. The published register assigns each entry a stable identifier, a revision date, an expiry or review date when relevant, the owner, and the status. Historical versions remain accessible so that an audit can match the wording published on a past campaign.
6. Distribute. Make the register available in the formats editors actually use: a CMS-controlled dropdown, a content style guide, a structured JSON file consumed by localization tooling, a controlled-vocabulary picker inside the email builder, and a slide-in library for copywriters. Distribution without enforcement reduces the register to documentation.
7. Audit. Sample recent marketing artifacts against the current register. Investigation is required when an off-register term is detected, when a defined term is used inconsistently, when a deprecated term resurfaces, or when a new variant diverges from the stated definition.

## Controls

The controls in this register focus on definition quality, change management, and consumption discipline rather than on writing prose in general.

- Every term has a definition, a source, an owner, and a status: preferred, restricted, banned, or deprecated.
- A deprecated term must remain in the register with an effective end date and a recommended replacement.
- Two terms cannot have overlapping definitions unless one is explicitly marked as a synonym for the other and the canonical entry is named.
- A restricted or banned term is gated by an editorial check before publication in any channel that consumes the lexicon.
- A revision requires change context: what changed, why, who approved, and the campaign or incident that triggered the change.
- Localization consumes the register through a translation memory binding; translated preferred terms propagate, but each locale may add a locale-specific synonym entry.
- AI-assisted copy tooling is configured against the register, with allowed-term and disallowed-term lists enforced at the prompt or output filter layer.
- An audit-ready export includes the register version, the export date, and a manifest of consumers that received the version.

## Validation evidence

Evidence that the lexicon is operating as a controlled vocabulary is collected periodically and on demand.

- A snapshot of the register at the time a campaign was published, matched against the campaign copy or creative.
- A sample of recent marketing artifacts scanned for occurrences of restricted or banned terms.
- A diff between the register version in production and the version approved at the start of the campaign window.
- A list of consumers (CMS, email, web, social tooling) and their last successful refresh against the register.
- An example of an editorial or automated block triggered when a restricted term was submitted.
- A record of any consumer that fell out of sync and the corrective action taken.

The intended outcome is that an external reviewer can answer: which words were allowed on a specific campaign, who approved them, and where the rule came from.

## Failure modes and correction

Common failures include definitions that are aspirational rather than operational, terms adopted from executive speech without translation into usable copy guidance, registers that are maintained only by the brand team and never reach operational tooling, parallel glossaries that contradict each other, deprecated terms that linger in long-lived landing pages, and AI prompts that bypass the register entirely. Another recurring failure is treating the lexicon as a marketing document rather than an authoritative input to legal, accessibility, and product language.

Correction starts with confining the immediate channel: stop using the offending term in new artifacts, downgrade any automated approvals that depend on it, and pause variant generation that depends on it. The lexicon entry is then updated: revise the definition, mark the term deprecated, propose a replacement, and document the date the change is effective. Updated register versions are pushed to all consumers and tested for adoption. When the failure originated upstream, such as an executive quote, the register entry captures the boundary condition. A post-incident review records why the failure was not caught earlier and identifies the control that needs to be tightened, the gating step, or the audit cadence.

## Limitations

The lexicon governance register does not determine whether a marketing statement is substantiated, whether a comparative claim is truthful, whether a disclosure is conspicuous enough, whether a privacy notice is compliant, or whether a translated term carries its intended meaning for the target audience. It does not adjudicate brand disputes, trademark conflicts, or rights of publicity. It assumes a workable feedback loop between the brand team and the operational tooling that publishes copy. Where that loop is broken, the register will not by itself prevent inconsistent use.

## Canonical sources

- **Primary authority 1 — ISO 704:2009, Terminology work — Principles and methods:** [https://www.iso.org/standard/38109.html](https://www.iso.org/standard/38109.html)
- **Primary authority 2 — ISO Online Browsing Platform (terminology catalogue index):** [https://www.iso.org/obp/ui/#iso:std:iso:704:en](https://www.iso.org/obp/ui/#iso:std:iso:704:en)
