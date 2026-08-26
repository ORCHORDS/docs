# California DROP data-broker deletion operations

**Issue:** Beginning August 1, 2026, a covered California data broker must retrieve and process requests through the Delete Request and Opt-out Platform (DROP) at least every 45 days. A one-time delete job is insufficient because associated personal information, including inferences, can exist across active systems, service providers, contractors, archives, and later acquisition feeds.

**Date:** 2026-08-18
**Author:** ORCHORDS
**Status:** documented

## Applicability and controls

- Confirm data-broker status, registration, DROP account, fee, and any statutory exception with California counsel and current CalPrivacy instructions.
- Assign an accountable identity for DROP access and a backup; use phishing-resistant authentication, least privilege, credential rotation, and access logging.
- Poll on a schedule comfortably inside 45 days and alert before the legal boundary.
- Match requests only with authorized identifiers and bounded logic; quarantine ambiguous matches rather than exposing whether a person exists in a dataset.
- Discover and delete associated personal information, including inferences, across systems and applicable service providers or contractors unless a documented legal exception applies.
- Report the required status in DROP within the applicable period after retrieval.
- Maintain a suppression control so deleted information is not simply reacquired, re-derived, or republished on the next ingest.
- Separate the minimum compliance audit record from the personal data being deleted and apply its own retention and access policy.

## Implementation and tests

Use a durable workflow with retrieval batch ID, receipt time, match decision, scoped systems, exception code and approval, deletion tasks, verification, provider acknowledgments, DROP status, and immutable completion evidence. Retry idempotently and reconcile every retrieved request to a terminal state.

Seed a synthetic identity through source, inference, export, audience, cache, backup, and downstream-provider paths. Verify deletion and suppression, then replay an ingest containing that identity. Test no match, ambiguous match, legal exception, provider timeout, partial failure, duplicate request, and a poller outage approaching 45 days.

## Gotchas and legal caveat

The 45-day requirements have distinct triggers; do not collapse platform access, processing, and status reporting into one unchecked timer. Deleting a source field while retaining an inference can remain incomplete. Exceptions must be specific and evidenced, not a blanket operational bypass.

This is engineering guidance, not legal advice. Verify the current California Civil Code, regulations, DROP instructions, and applicability before relying on it.

## Official sources

- [California Privacy Protection Agency: Information for data brokers](https://cppa.ca.gov/data_brokers/)
- [CalPrivacy: California approves Delete Act regulations](https://cppa.ca.gov/announcements/2025/20251113.html)
- [California DROP portal](https://privacy.ca.gov/data-brokers/)
