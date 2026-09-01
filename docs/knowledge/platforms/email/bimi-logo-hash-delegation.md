# BIMI Logo Hash Delegation Records

Most BIMI deployments publish one logo per domain and stop there. Hash delegation is the mechanism for everything more ambitious: a selector namespace under `_bimi` that lets one domain serve different marks to different mail streams, and a hash-pinning field that lets the owner assert the exact bytes of the logo an authority has vetted. The selector record - `sel1._bimi.example.com` alongside `default._bimi.example.com` - is how a platform sending on behalf of a brand can carry a mark distinct from corporate mail, selected via a `BIMI-Selector` header the sending MTA injects. The hash tag pins a digest of the logo so a mailbox provider can confirm the fetched SVG is the artifact that was validated, not a substituted file. Neither piece is mandatory, but together they make multi-logo setups governable and third-party delegation auditable.

## Scope

This article covers the DNS mechanics of BIMI selectors and hash pinning: selector record discovery, how the BIMI-Selector header drives selection, what the hash field binds, and how multi-logo and delegated-sender arrangements are configured and audited. It is aimed at operators running BIMI across multiple streams or brands. It excludes VMC issuance and trademark evidence, SVG profile constraints, and mailbox-provider UI policies deciding whether a logo renders at all.

## Workflow or implementation guidance

A multi-logo deployment proceeds in four phases.

**Phase 1 - inventory streams.** Enumerate the sending streams on the organizational domain: corporate mail, transactional systems, marketing campaigns, third-party platforms sending under the domain's name. Decide per stream whether it carries the corporate mark, a stream-specific mark, or no mark. The no-mark case matters: BIMI records inherit from the organizational domain to subdomains, so suppressing display requires deliberate action - a no-image selector or an omitted record where scoping allows.

**Phase 2 - publish the selector lattice.** Publish the default record at `default._bimi` on the organizational domain so inheriting subdomains resolve it. For each distinct stream mark, publish a record under a named selector - `newsletters._bimi`, say - containing the logo location and, where applicable, the hash of the vetted logo. Keep TTLs modest during rollout so mistakes revert quickly.

**Phase 3 - wire the selection.** Configure the sending MTA to add `BIMI-Selector: v=BIMI1; s=<selector>` on streams using a non-default mark. The header travels with the message; the provider resolves `<selector>._bimi.<From domain>` instead of the default location. Absence of the header means the default record governs. Injection must happen before DKIM signing, and the header should be signed so a selector cannot be swapped in transit.

**Phase 4 - pin and audit.** Where an authority has validated the logo, include the hash in the record referencing that validation. Maintain a registry mapping each selector to logo file, hash, artwork version, and validation evidence. When artwork changes, recompute, re-validate where required, and update the record - a stale hash against a new file is a hard display failure, which is precisely the tamper signal the field exists to produce.

For delegation to a platform sending on your behalf, the From domain stays yours, so selector records remain in your DNS and you retain veto authority over every mark; the platform's only leverage is the header it injects, which your signing policy governs.

## Controls

- Selector naming convention with change control, reviewed like any published DNS record.
- Default-record coverage check: every subdomain that should display the corporate mark resolves to it through inheritance or an explicit record.
- Hash freshness gate in the publish pipeline blocking DNS updates when the record's hash does not match the validated artifact.
- BIMI-Selector header signing: the header appears in `h=` for streams using non-default selectors.
- Header injection ordering: emitted before the signature, never after.
- Quarterly selector-to-stream reconciliation via an independent resolver walk.
- Delegation audit: platforms may only select from selectors you publish; monitor for unexpected selector values in your authenticated streams.
- TTL discipline: short during changes, raised once stable.

## Validation evidence

- Resolver queries proving `default._bimi.<domain>` and each named selector return the intended records from outside your network.
- A digest comparison showing the published hash equals the hash of the served SVG, computed independently of the publishing pipeline.
- Message captures per stream demonstrating the BIMI-Selector header is present, correctly valued, and covered by DKIM.
- Display confirmation per participating provider for each selector, since selector support varies by platform.
- Inheritance test: a subdomain with no local record resolves the organizational default; a no-image selector suppresses display as designed.
- Audit log of every selector change with the triggering artwork version.

## Failure modes and correction

A stream showing the corporate logo where a distinct mark was intended is almost always the BIMI-Selector header missing, misspelled, or added after signing; fix the injection order and confirm `h=` coverage. A stream showing nothing where the default should apply, on providers with partial selector support, indicates the platform resolved a selector path it does not fully honor; test on a provider known to support selectors before blaming your DNS. Hash mismatch failures look like fetch problems but are pinning working correctly: the served file diverged from the pinned digest after an artwork swap that skipped the record update - re-pin deliberately. Subdomains unexpectedly displaying a logo mean inheritance is doing its job and you wanted a no-image selector there. A platform presenting marks you did not authorize points to a selector header you do not sign; bring the stream under your signing policy or revoke the platform's ability to send as the domain. Stale records after brand refreshes are caught by the quarterly reconciliation, which exists because selector lattices grow quietly.

## Limitations

Selector support is not universal across mailbox platforms, and the BIMI Group's own guidance warns that support varies between email platforms; a fully correct lattice can still render inconsistently. Hash pinning only constrains providers that verify the digest, so it is a tamper signal rather than a tamper proof. The BIMI-Selector header is a sender-side assertion - receiver behavior on unknown selectors, malformed values, or conflicting records is a provider implementation detail. Multi-logo setups multiply the DNS surface that must stay consistent with artwork and validation evidence, and nothing in the mechanism refreshes hashes automatically. Delegation here concerns display assets only; actual sending authority remains an SPF, DKIM, and DMARC question.

## Canonical sources

- [BIMI Group: FAQ (selectors, multiple logos, BIMI-Selector header)](https://bimigroup.org/faq/)
- [BIMI Group: Implementation Guide](https://bimigroup.org/implementation-guide/)
- [BIMI Group: Supporting Documents](https://bimigroup.org/supporting-documents/)
- [RFC 6376: DomainKeys Identified Mail (DKIM) Signatures (h= signed header list)](https://www.rfc-editor.org/rfc/rfc6376.html)
- [AuthIndicators Working Group GitHub organization](https://github.com/authindicators)
