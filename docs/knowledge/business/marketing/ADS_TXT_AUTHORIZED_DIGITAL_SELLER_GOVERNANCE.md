# Authorized Digital Sellers (ads.txt) Governance

## Scope and control objective

For ads.txt, control point 2: this article governs web inventory seller authorization. Its purpose is to make implementation decisions reproducible across marketing, engineering, legal, privacy, security, and vendor teams. It applies to production domains, applications, accounts, campaigns, and processors that create, transform, publish, transmit, or enforce the relevant information. Adoption is not a guarantee of legal compliance, delivery, display, indexing, or platform acceptance. The normative baseline for ads.txt is the cited specification or legislation; workflow cadence, peer review, automation, and evidence packaging stated here are recommendations unless an adopted policy makes them mandatory.

For ads.txt, control point 3: before approval, record the organization’s role, applicable jurisdictions, authoritative version, systems in scope, and exclusions. The review boundary includes publisher domains, exchange account IDs, DIRECT/RESELLER relationships, certification authority IDs. DNS changes, account migrations, tag-manager releases, identity changes, vendor routing, and application updates can invalidate an approval even when creative is unchanged.

## Inventory and ownership

For ads.txt, control point 5: assign one accountable business owner and one technical custodian. Maintain an inventory linking each public property or sending system to its internal owner, vendor, identifiers, processing purpose or commercial relationship, activation date, and retirement state. Reconcile public identifiers to contracts and platform systems; never infer them from display names.

For ads.txt, control point 6: document the end-to-end path: originator, each intermediary, represented party, recipient, identifiers transferred, and the point where authorization or consumer choice is enforced. Uncertain legal classifications require qualified review, not an unsupported technical conclusion. Vendors must identify downstream dependencies and correction contacts before onboarding.

## Release workflow

1. Open a change record naming the exact production artifact and owner.
2. Reconcile proposed values against active accounts, contracts, authorization, and current identity evidence.
3. Generate controlled output where practical; peer-review hand-authored data.
4. Crawl root files; reconcile every record to contracts and exchange consoles; test redirects and parsers.
5. Exercise a valid case, an intentionally invalid or unauthorized case, and a recovery case.
6. Publish using least privilege and capture the deployed version or cryptographic hash.
7. Verify externally after publication, allowing for relevant DNS, HTTP, mailbox, browser, store, or platform caches.
8. Approve only observed production behavior, not a draft screenshot or generic vendor assurance.

For ads.txt, control point 9: tests should cover meaningful variants: direct and intermediary routes, logged-in and anonymous states, subdomains, mobile and desktop clients, locale variants, and failure responses where applicable. Syntax success is insufficient when values are semantically wrong.

## Preventive controls

For ads.txt, control point 11: separate commercial activation from technical verification. Restrict publishing privileges, require reviewed changes, validate identifiers against an inventory, and protect signing keys and bearer tokens. Do not expose secrets or unnecessary personal data in public artifacts. Block onboarding until evidence is complete.

For ads.txt, control point 12: contracts should allocate responsibility for identifiers, downstream propagation, correction timing, incident notice, and offboarding. Retirement must remove residual public declarations, cached audiences, routing, and partner permissions. Disabling a visible campaign alone does not prove processing ended.

## Monitoring and validation evidence

For ads.txt, control point 14: monitor production at a cadence proportionate to impact and change frequency. Fetch or exercise controls from outside the corporate network. Alert on semantic changes, missing fields, authentication failures, unexpected recipients, stale entries, and invalid responses. Compare observed state to the system of record and investigate every unexplained addition.

For ads.txt, control point 15: retain the source version, change ticket, inventory snapshot, approval, deployed artifact, parser or validator output, representative transaction, negative test, recovery test, and downstream acknowledgment. Record expected and actual results, tester, reviewer, timestamp, environment, and tool version. Mutable dashboards are corroboration, not durable evidence. Use the approved records schedule rather than inventing a universal retention period.

## Failure handling

For ads.txt, control point 17: topic-specific failure modes include stale reseller routes, wrong relationship values, unauthorized account IDs. General failures include malformed-but-accepted data, stale vendor routes, partial propagation, cache confusion, unauthorized additions, and controls present in a user interface while server-side processing continues.

For ads.txt, control point 18: classify impact promptly: misrepresentation, unauthorized distribution, lost consumer choice, security exposure, interruption, or reporting discrepancy. Contain affected routes when continued operation compounds harm. Preserve logs and served artifacts before changing state, then notify accountable technical and governance owners under the incident plan.

For ads.txt, control point 19: correct the authoritative source first and regenerate dependent outputs; hand-editing generated products creates drift. Repeat positive, negative, and recovery tests. Monitor through propagation windows and obtain downstream confirmation. Close only when production evidence matches intended state. Repeated incidents require root-cause analysis and an automation, testing, ownership, or contract improvement.

## Limitations and periodic review

For ads.txt, control point 21: at least quarterly, and after material platform or regulatory change, sample active and retired entries, confirm ownership, retest rollback, and review the canonical publication for revisions. Acquisitions, new subdomains, processor changes, and platform migrations trigger immediate reassessment. Version changes and migration decisions must be documented; claims must never exceed what current evidence and the authoritative source support.

## Canonical sources

- [Additional canonical source](https://github.com/InteractiveAdvertisingBureau/adstxt)

- [IAB Tech Lab ads.txt](https://iabtechlab.com/ads-txt/)
