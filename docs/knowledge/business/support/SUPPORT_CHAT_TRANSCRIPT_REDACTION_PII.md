# Support Chat Transcript Redaction PII

## Scope

This article governs how the support desk redacts personally identifying information from a chat transcript before the transcript is moved out of the operational case store into a longer-lived analytics or training store. The scope covers transcripts generated in synchronous chat, in asynchronous messaging (email-like chat windows that survive across sessions), and in in-product chat widgets. It does not cover voice transcripts, which use a different redaction pipeline, and it does not cover transcripts that never leave the operational store (which are governed by the operational store's own access controls).

The discipline follows the privacy handling principles codified in ISO/IEC 27018 for protection of personally identifiable information in public cloud services acting as PII processors, and the broader principle of data minimisation found in privacy regulation. The goal is not to anonymise the transcript to a level that supports public release; it is to reduce the transcript to the minimum data the receiving store requires for its stated purpose.

## Workflow or implementation guidance

Redaction begins with a defined classification of fields. Each field in the transcript carries a sensitivity class, and each class carries a redaction rule. The classes typically include: free-text customer message, free-text agent message, structured case fields (case identifier, channel, timestamps), and free-text notes added by the agent. The free-text fields are the high-risk class; the structured fields are the low-risk class.

For free-text fields, the redaction pipeline identifies candidate spans and replaces them with a typed token. A span is a candidate if it matches a defined pattern (credit card, national identifier, email, phone, account identifier) or if it is flagged by a high-recall named-entity recogniser. The replacement token records the class but not the original value; for example, `[REDACTED:CARD]`, `[REDACTED:EMAIL]`, `[REDACTED:NAME]`. The token preserves the syntactic structure of the message so that the receiving store can still perform useful analysis on shape, length, and intent, without the underlying identifying value.

The pipeline runs in two passes. The first pass applies the high-recall patterns; the second pass applies the named-entity recogniser with a high-precision threshold. The two-pass design protects against false positives (a legitimate word that matches a credit-card pattern) while still catching the long tail of identifying content. The patterns and the recogniser threshold are reviewed quarterly, because the long tail changes as the chat patterns change.

For structured fields, redaction is simpler. The case identifier is preserved (it is the join key); the agent identifier is preserved; the channel and timestamps are preserved. Any field that is not on the allow-list is dropped at export time. The allow-list is enforced at the export job, not at the field-level redaction step, so the operational case store continues to carry the full data and only the export is reduced.

Redaction is paired with a retention policy. The redacted transcript carries a retention class that determines when it is deleted from the analytics store. The retention class is set by the data owner and is consistent across the analytics environment. The original transcript in the operational store carries its own retention class, which is typically shorter because the operational need expires with the case.

## Controls

Controls are layered. At the pipeline layer, the redaction job is implemented as a deterministic function that can be replayed against the source transcript; the redacted output and the source transcript are stored separately, with the redacted output carrying a hash of the source. The hash makes the audit trail reproducible without exposing the source. At the storage layer, the analytics store enforces a separate access role list from the operational store; the analytics roles do not include the data subjects themselves. At the export layer, the export job records every field it carries, and a periodic audit compares the recorded fields against the allow-list.

A separate control protects against a redaction regression. A small set of synthetic transcripts with embedded identifying content is maintained; the synthetic transcripts are run through the redaction pipeline on every change, and the output is compared against the expected output. If a regression is detected, the change is reverted before it reaches production.

## Validation evidence

Validation is exercised continuously. The redaction pipeline logs its decisions at the span level: the position, the matched pattern or entity, and the replacement token. The logs are sampled to confirm that high-recall patterns are matching as expected and that the named-entity recogniser is not over-redacting. The synthetic regression suite is run on every change and on a fixed schedule. A periodic privacy review compares the analytics store schema against the allow-list and confirms that no off-list field is present.

## Failure modes and correction

The most common failure is a missed pattern: a new identifier format is introduced (for example, a new type of national identifier), and the redaction pipeline doesn't recognise it. The correction is the quarterly review of patterns, plus a feedback channel that lets analysts flag a missed identifier so the pattern set can be updated.

The second most common failure is over-redaction that destroys the analytical value of the transcript. A high-precision threshold that is too aggressive turns a useful transcript into a wall of tokens. The correction is the two-pass design and the periodic review of the recogniser threshold. The owner balances false positives against false negatives and adjusts accordingly.

The third most common failure is the silent export of a non-allow-listed field. The correction is the export allow-list enforcement at the job level and the periodic audit.

## Limitations

Redaction is a statistical process, not a guarantee. A determined adversary with access to the redacted transcript and to external side information may be able to re-identify some content. The pipeline reduces the risk; it does not eliminate it. The data owner is responsible for confirming that the residual risk is acceptable for the receiving store.

Redaction also assumes that the receiving store does not need the identifying content for its analytical purpose. If the receiving store requires the content (for example, for personalised analytics), redaction is the wrong approach and the data should either remain in the operational store or be subject to a stronger governance regime.

## Canonical sources

- ISO/IEC 27018:2019, Code of practice for protection of personally identifiable information in public clouds acting as PII processors (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- NIST SP 800-122, Guide to Protecting the Confidentiality of PII, https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-122.pdf
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- OWASP, Cheat Sheet Series, Logging and Error Handling, https://cheatsheetseries.owasp.org/