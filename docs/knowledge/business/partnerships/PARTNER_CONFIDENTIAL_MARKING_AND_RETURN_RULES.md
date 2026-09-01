# Partner Confidential Marking and Return Rules

Most confidentiality obligations in partner NDAs are conditioned on form: information must be marked, or identified in writing within a fixed period after oral disclosure, and returned or destroyed on request or at termination. Each of those conditions is an operational trap if the receiving organisation cannot find, label, and retrieve what it holds. This article covers marking thresholds, the oral-disclosure write-down duty, and return/destruction obligations as managed operational controls rather than boilerplate.

## Scope

Applies to partner relationships where confidential information flows in both directions under an NDA with marking, identification, and return provisions. In scope: what counts as adequate marking, how to run the oral-disclosure confirmation cycle, how to inventory holdings, and how to execute return or destruction with certificates. Out of scope: the definition of confidential information itself, residuals treatment, and the security controls around storage, which are separate disciplines. The accountable role is the **information exchange controller**; every named individual recipient carries personal duties under the regime.

## Workflow or implementation guidance

Set the marking threshold before the first exchange. The standard formulation requires legended documents and a written confirmation for unmarked or oral disclosures within a defined period — commonly fifteen or thirty days. Three practical questions decide the regime: does a failure to mark or confirm forfeit protection entirely, only create a presumption of non-confidentiality, or leave an exception for information that a reasonable person would understand to be confidential; who must send the written confirmation, the discloser summarising or the receiver acknowledging; and does the clock run from disclosure or from a subsequent written reminder. Capture the answers in a one-page exchange protocol both teams sign, because operating staff will never parse the NDA to find them.

Run the oral-disclosure write-down duty as a closed loop. When technical content is disclosed in a meeting or call, the discloser's delegate drafts a short summary identifying the items claimed as confidential, dates it, and sends it to the receiver's delegate within the contractual window. The receiver either corrects the summary, disputes the confidentiality claim, or lets it stand. File the summary, any correction, and the outcome in the disclosure log. Unconfirmed oral content has no protection under a strict marking clause, and the log is the only way either side can later establish what was claimed and when.

Inventory holdings continuously. Register every channel through which confidential materials arrive — shared workspaces, email attachments, ticket attachments, test data transfers, repository access — and log each delivery with a unique identifier, date, sender, recipient group, and legend status. The inventory is what makes a return obligation executable; without it, "return all confidential information" is executed by email search under deadline pressure.

Execute return or destruction on the trigger events: written request, termination of the underlying agreement, or expiry. The standard clause permits retention of one archival copy for legal-compliance purposes and of copies in routine backup cycles from which recovery is impractical; confirm which carve-outs the agreement actually contains, and preserve the same carve-out for the partner's materials as you rely on for your own. Produce a certificate of destruction or return listing item identifiers, not titles alone, and require the same granularity from the partner.

Close the loop with access revocation: remove repository grants, portal accounts, distribution-list memberships, and shared-folder permissions tied to the exchange, and record revocation dates. Backup-tape expiry or inability to selectively delete should be disclosed in the certificate rather than silently absorbed.

## Controls

- Exchange protocol document stating marking format, confirmation window, confirmation sender, and effect of failure to mark.
- Disclosure log with unique identifiers for every delivery, oral-confirmation summaries attached to their entries.
- Marking exception register recording any unmarked materials later claimed confidential and how each claim resolved.
- Return/destruction runbook defining scope, certificate template, carve-outs invoked, and access-revocation checklist.
- Dual sign-off on certificates: the information exchange controller and the project lead confirm completeness against the disclosure log.
- Periodic audit sample matching held materials in the shared workspace against the disclosure log to detect unregistered flows.
- Personnel off-boarding hook that checks departing staff against active exchange registers.

## Validation evidence

Artifacts include the signed exchange protocol, the disclosure log with per-item identifiers, oral-disclosure summaries and their responses, return and destruction certificates with item-level lists, access-revocation records, and audit-sample findings. Validate by selecting ten disclosure-log entries and confirming each has a corresponding artefact class — legend, written confirmation, or registered exception. Then reverse the test: sample files in the exchange workspace and confirm each traces to a log entry; orphan files indicate unregistered receipt, which breaks both marking and return mechanics. Reconcile certificates against the log for completeness: every logged item is returned, destroyed, or covered by an invoked and documented carve-out. Retain certificates and logs past the agreement's survival period for confidentiality, since survival terms commonly outlive the return obligation itself.

## Failure modes and correction

Recurring failures: marking windows missed on fast-moving technical calls, leaving valuable disclosures unprotected; summaries written to be maximally broad, which receivers rightly reject and which poison the confirmation process; return executed as a bulk folder deletion that destroys audit trails along with materials; backup carve-outs invoked without disclosure, creating latent possession the partner can later discover; and the disclosure log abandoned once the relationship normalises. Correct missed confirmations where the agreement permits by sending a late identification and recording whether it was contested. For orphan files, register them retroactively with an honest receipt date rather than a fabricated one. Where destruction would harm legal holds, segregate the materials under a documented hold carve-out instead of deleting selectively and claiming full compliance.

## Limitations

Marking regimes reward administrative discipline and can strip protection from genuinely sensitive content simply for want of a legend; jurisdictions differ on how strictly that consequence is enforced, so the regime here is operational risk management rather than a statement of law. Routine-backup carve-outs mean destruction is never literally total. Confirmation cycles add latency to collaboration and are frequently resented by engineers; the protocol must assign the duty to named delegates or it will not happen.

## Canonical sources

- OECD — Protection of confidentiality of data, governing guidelines: https://www.oecd.org/sti/
- ICC — Model contracts including confidentiality provisions: https://iccwbo.org/business-solutions/model-contracts/
- WIPO — Trade secrets resources: https://www.wipo.int/
