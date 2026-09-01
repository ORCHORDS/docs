# Support Ticket to Article Mining

Resolved tickets are the desk's richest source of knowledge: they contain real customer language, real failure conditions, and real verified fixes. Mining them into published articles turns a private answer into a reusable asset, but only if the desk selects the right tickets, strips what must not be published, and routes the draft through review by someone accountable for correctness. This article covers the mining pipeline from selection to publication.

## Scope

This article governs the practice of converting resolved support tickets into public or internal knowledge-base articles: which tickets qualify, how customer and sensitive content is removed, who drafts and who approves, and how the resulting article is validated after publication. It applies to tickets from every channel once resolved and verified.

It does not cover real-time article suggestion to agents during a live ticket, knowledge-centered service process adoption broadly, or article retirement (covered by workaround-expiry and related articles in this folder). It assumes an article review board or an accountable content owner exists; without one, mining must not publish externally.

## Workflow or implementation guidance

The pipeline has eight steps:

1. Candidate detection. Weekly, query resolved tickets for mining signals: a resolution note referencing a documented cause, a fix verified by the customer, at least one reopen-and-close cycle that clarified the true cause, and topic frequency above a threshold (a topic seen three or more times in the period). Tickets closed as duplicates or cannot-reproduce are excluded from candidate selection.
2. Eligibility gate. A ticket is eligible only if the fix is generalizable (works for any customer with the symptom, not just this account's configuration) and the resolution is confirmed by both the agent and a system or customer signal. One-off account repairs become internal notes, not articles.
3. De-identification pass. The drafter strips names, email addresses, account numbers, order identifiers, hostnames, IP addresses, tokens, file paths that reveal directory structure, and any free text describing the customer's business. The replacement is a role ("a customer", "an administrator") and a generic environment ("a managed tablet", "a shared mailbox"), never a lightly disguised version of the original. Screenshots are excluded unless redrawn with synthetic data.
4. Draft assembly. The drafter writes the article from the ticket's evidence, not from memory: symptom in customer words (paraphrased), conditions, diagnostic steps, fix, verification, and when to contact support instead. The draft cites the ticket identifier internally so provenance survives.
5. Sensitive-content review. A second reviewer who did not draft runs a checklist against the draft: no personal data, no credentials, no non-public security detail, no unpatched-vulnerability specifics, no commitment language beyond policy. Automated scanning for identifiers supplements but does not replace the human pass.
6. Technical approval. The product or engineering owner for the affected component confirms the cause and fix are current and not about to change.
7. Publication with metadata. The article publishes with topic tags, effective date, owner, review-by date, and the mining batch identifier.
8. Post-publication validation. After thirty days, check whether the article is being found (search terms, views), whether the topic's ticket rate declined, and whether feedback flags report inaccuracies; feed results into the next mining cycle's selection.

The provenance link between article and source ticket is internal-facing only, and access to it is restricted, because the ticket retains personal data the article must not carry.

## Controls

- Dual review: no mined article publishes without both a sensitive-content reviewer and a technical approver, recorded with date and version.
- De-identification test: before publication, the draft is searched against the source ticket's distinctive strings; a match blocks publication. Distinctive-string testing catches paraphrase failures that manual review misses.
- Security disclosure gate: any ticket whose cause involves a vulnerability, exposed data, or abuse technique routes to the security disclosure process instead of the public knowledge base; publication waits for the coordinated disclosure decision.
- Review-by date enforcement: every mined article carries a review-by date; overdue articles are unpublished or flagged stale rather than left unreviewed.
- Rate-decline attribution check: the desk verifies that a claimed reduction in ticket volume for a mined topic is not explained by a concurrent product fix, before crediting the article.

## Validation evidence

Evidence for a mining batch: the candidate list with eligibility verdicts and exclusion reasons; de-identification check results per article (distinctive-string scan output); dual-review and technical-approval logs; publication metadata including review-by dates; and the thirty-day validation report linking each article to search performance, feedback, and topic ticket-rate movement. A periodic audit re-reads a sample of published mined articles against their source tickets to confirm no personal data leaked and the fix still holds.

## Failure modes and correction

Personal-data leakage through paraphrase is the most serious failure: the drafter generalizes the symptom but keeps a distinctive detail (a rare hostname, an unusual business description) that identifies the customer. Correction: distinctive-string scanning, second-reviewer checklist, and immediate unpublish-and-rewrite on discovery, with a leak register entry.

The stale-on-arrival article is second: the product changed between resolution and publication, and the fix no longer works. Correction: technical approval must be within a defined window of publication, and the review-by date for mined articles is short (90 days) because they are born from a specific product state.

The one-off masquerading as general is third: the fix depended on the account's configuration, and other customers fail the article's steps. Correction: the eligibility gate's generalizability test, plus post-publication feedback routed to the article owner for reclassification.

The unfindable article is fourth: correct, approved, and never surfaced. Correction: the thirty-day validation step revises titles and tags using the customer's own words from the source tickets.

## Limitations

Mining is retrospective; it cannot cover emerging issues still under diagnosis. Volume thresholds mean rare-but-severe topics may need a manual exception path. Translation of mined articles into other languages follows the separate translated-knowledge parity discipline and inherits its costs. Where tickets lack structured resolution notes, candidate detection degrades to manual selection and throughput drops sharply; the desk should fix resolution-note discipline before scaling mining.

## Canonical sources

- NIST SP 800-53 Rev. 5, System and Services Acquisition control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- NIST SP 800-122, Protecting the Confidentiality of Personally Identifiable Information (PII), https://csrc.nist.gov/pubs/sp/800/122/final
- W3C, Web Content Accessibility Guidelines (WCAG) 2.2, https://www.w3.org/TR/WCAG22/
