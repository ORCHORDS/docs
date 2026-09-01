# Marketing Email List Hygiene and Bounce Classification

A mailing list is a store of promises: each address carries an implied assertion that the person behind it still wants the mail and that the address still works. This article governs how marketing teams classify delivery failures, how long addresses remain on active lists after failures, and how list-sunset rules and one-click unsubscribe honoring are enforced so that hygiene decisions are reproducible and defensible. Poorly classified bounces produce either over-aggressive removal of reachable customers or, more commonly, continued mailing to dead addresses, which degrades sender reputation and signals that consent practices are not actually under control.

## Scope

This control applies to every address used for marketing or promotional email: newsletter lists, lifecycle programs, win-back campaigns, imported lists, co-registration sources, and addresses collected at offline events. It covers bounce classification at ingestion of delivery status notifications, suppression list management, list-sunset decisions, and the technical honoring of unsubscribe signals including the one-click List-Unsubscribe-Post mechanism.

It does not cover the initial legality of consent collection, CAN-SPAM or GDPR substantive obligations, or content review; those belong to separate controls. It intersects with those controls at one point: an unsubscribe signal or a persistent bounce must produce suppression that is honored by every sending system, not only the one that observed the signal.

## Workflow or implementation guidance

1. **Classify at ingestion, not at reporting time.** Delivery status notifications and SMTP replies are parsed when they arrive and each failed recipient is tagged with a bounce class: persistent (hard), transient (soft), or unclassifiable. Classification rules map SMTP reply codes and enhanced status codes to classes; anything ambiguous defaults to transient, never to persistent, because misclassifying a live mailbox as dead is the costlier error.
2. **Distinguish the two failure families precisely.** Persistent failures include nonexistent mailboxes, domains with no mail exchanger, and syntactically invalid addresses. Transient failures include full mailboxes, temporary DNS failures, greylisting deferrals, throttling responses, and provider-side temporary blocks. A transient failure that persists across a defined window is re-examined before any removal decision.
3. **Score addresses on a rolling window.** Each address accumulates a bounce history with timestamps, classes, and the sending campaign. A sunset candidate is an address whose recent history meets the sunset rule, for example a defined number of persistent bounces or a defined count of transient bounces with no successful delivery inside a stated window.
4. **Sunset to a holding state, not to deletion.** Addresses meeting the rule move from active lists to a sunset state where they are excluded from campaign selection but retained as a suppression key for the retention period. Deletion follows the records schedule and any legal hold, not the hygiene trigger.
5. **Re-permission, do not silently reactivate.** An address that later delivers successfully again, or whose owner resubscribes through a verified flow, re-enters active state through an explicit event. Recovery by list import is blocked: importing an address that exists in the sunset or suppression state does not reactivate it without the verified resubscription event.
6. **Honor one-click unsubscribe at the protocol layer.** Marketing mail carries List-Unsubscribe and List-Unsubscribe-Post headers; a POST to the unsubscribe URL suppresses the recipient across all sending systems without requiring sign-in, additional clicks, or profile changes. The endpoint is idempotent: repeated POSTs produce the same suppressed state.
7. **Reconcile weekly.** A reconciliation job compares the suppression state observed by each sending system and vendor against the central suppression store, and flags any address that received mail while suppressed.

## Controls

- Bounce classification rules are versioned and owned; a change to the rules is a reviewed change with an effective date, because classification drives irreversible suppression.
- Sunset thresholds are configuration with named owners, not hardcoded values scattered across tools.
- No sending path may bypass the central suppression check; batch exports to vendors are filtered through suppression at export time and again at send time.
- Unsubscribe endpoints accept anonymous POSTs, require no authentication that the recipient cannot possess, and validate tokens without exposing recipient identifiers in query strings.
- List imports carry a source declaration and are quarantined until hygiene checks run: syntax validation, known-bounce matching, and suppression matching.
- Complaint feedback loops are treated as hygiene signals with the same authority as bounces: a complaint drives suppression review, not a deliverability discussion.

## Validation evidence

- Bounce classification logs for a representative period, showing raw SMTP responses, assigned classes, and the rule version applied.
- Sunset decision records: for a sample of removed addresses, the bounce history that triggered the rule and the rule version in force.
- One-click unsubscribe test transcripts: a POST with a valid token returning success, a repeat POST confirming idempotence, a forged or expired token failing safely, and subsequent campaign selections excluding the address.
- Vendor reconciliation reports showing zero unsuppressed sends, with exceptions and their dispositions.
- Audit records for every rule or threshold change, including the rationale and the approver.

## Failure modes and correction

Typical failures include classifying greylisting as persistent and removing reachable customers, treating a full mailbox as permanent, re-importing a suppressed address through a spreadsheet, a vendor honoring suppression only on the list it observed, an unsubscribe endpoint that requires login and therefore does not honor the one-click mechanism, and a sunset rule tuned so loosely that dead addresses remain active for quarters. A subtler failure is asymmetry: the marketing platform honors suppression but a transactional system sharing the same vendor account does not, so the customer concludes the opt-out was ignored.

Correction begins with quantification: identify the misclassified population, the rule version, and the date range. Erroneously suppressed addresses are restored and mailed with an apology where appropriate; the classification rule is corrected and re-tested against archived SMTP responses before deployment. Vendor bypasses are fixed contractually and technically, and the weekly reconciliation is rerun until clean. Recurrence of import-based reactivation triggers removal of import privileges from non-privileged roles.

## Limitations

Bounce classification is inference from protocol signals; providers differ in the replies they emit, and some temporary conditions last longer than any reasonable transient window. Sunset rules trade reach against reputation, and the thresholds stated here are governance defaults, not industry mandates. This control does not determine whether the underlying consent to mail was lawful, and it cannot compel third-party vendors to expose the instrumentation needed to verify their suppression behavior beyond what contracts require. Deliverability outcomes depend on receiving-provider policies outside the organization's control.

## Canonical sources

- **Primary authority 1 — RFC 5321, Simple Mail Transfer Protocol (reply code and status code semantics):** [https://www.rfc-editor.org/rfc/rfc5321](https://www.rfc-editor.org/rfc/rfc5321)
- **Primary authority 2 — RFC 8058, Signaling One-Click Functionality for List Email Headers:** [https://www.rfc-editor.org/rfc/rfc8058](https://www.rfc-editor.org/rfc/rfc8058)
- **Reference — RFC 3463, Enhanced Mail System Status Codes:** [https://www.rfc-editor.org/rfc/rfc3463](https://www.rfc-editor.org/rfc/rfc3463)
