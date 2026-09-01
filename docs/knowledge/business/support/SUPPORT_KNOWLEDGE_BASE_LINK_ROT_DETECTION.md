# Support Knowledge Base Link Rot Detection

## Scope

This article governs how the support desk detects and corrects link rot in its knowledge base. Link rot is the phenomenon by which a URL cited in a knowledge article no longer resolves to the resource the article expected. The cause may be a typo at the time of authoring, a server migration by the cited party, a domain expiry, or a deliberate takedown. The effect on the support desk is that a customer following the article reaches a dead end, and the article's credibility is damaged.

The scope covers every outbound link in a knowledge article, including links to product documentation, regulatory guidance, partner portals, status pages, and external authorities. It does not cover inbound links from external sites to the knowledge base; those are governed by a separate search-engine optimisation discipline.

## Workflow or implementation guidance

Detection runs on two cadences. A lightweight cadence runs continuously and checks a small set of representative links; a heavier cadence runs weekly and checks every outbound link in the published knowledge base. The link checker resolves the link, follows any redirects, and records the final HTTP status. A link that returns 4xx or 5xx, or that returns a 200 but with a substantive change in content, is flagged for review.

The substantive change check is necessary because a URL can return 200 and still be wrong. A link that previously pointed to a product FAQ now points to a marketing landing page; the link is technically live, but the content no longer matches the article's reference. The check is performed by hashing the body of the response at the time of the original authoring and comparing it to the current body. The hashes are stored alongside the link in the link database.

When a link is flagged, the owner of the article is notified. The owner reviews the article and the linked resource, and either confirms that the article still works (in which case the flag is cleared and the link database is updated), finds a replacement link (in which case the article is updated and the link database is updated), or retires the article (in which case the article enters the deprecation workflow).

The owner has a defined response window. For a customer-facing article, the window is short because a broken link is a customer-impacting incident. For an internal agent article, the window is longer because the impact is contained. A link that is not addressed within the window is escalated.

## Controls

Three controls protect the link database. The first is the schema: every link in the knowledge base is recorded with a stable identifier, the article it appears in, the position in the article, the timestamp of the original authoring, and the expected content hash. The schema is enforced at the publishing tool; a link that is not recorded cannot enter the article. The second control is the versioning: every article revision that adds, removes, or changes a link triggers a re-check of the affected links. The third control is the audit: a periodic review confirms that the link database matches the published articles.

A separate control protects against false negatives. A link checker that uses a single User-Agent string may be served a different response than a human customer would see. The check uses a User-Agent that mimics a real browser and that accepts common content encodings. The check also respects the target site's robots.txt; a site that asks not to be crawled is recorded as "opt-out" rather than as a broken link.

## Validation evidence

Validation evidence is collected continuously. The link check log records every check, the result, and the timestamp. The link database records every link with its history. The audit compares the link database against the published articles. A periodic tabletop exercise takes a sample of recent breakages and confirms that the detection found them, the owner was notified, and the resolution was appropriate.

## Failure modes and correction

The most common failure is a link checker that records a 200 without checking the content hash. The URL resolves, but the page is a different page than the one the article expected. The correction is the content-hash comparison and the per-link content expectation.

The second most common failure is the link checker being throttled by the target site. A site that receives too many automated requests may start returning error pages, which the checker records as breakages. The correction is rate limiting on the checker side and the use of opt-out recording for sites that ask not to be crawled.

The third most common failure is the link rot window being too long. A link that broke on day one and is fixed on day thirty leaves a month of broken-link impact. The correction is the response window and the escalation when the window expires.

## Limitations

The link rot discipline assumes that the content hash is stable. Where the cited site is a wiki or a frequently updated page, the hash changes regularly and the comparison produces too many false positives. The discipline should be applied in proportion to the volatility of the cited site, with a more permissive comparison for known-volatile sources.

The discipline also assumes that the link checker can reach the cited site. Where the cited site is behind a paywall or a login, the checker cannot perform the hash comparison and the link is recorded as "unverified". The organisation should accept that some links will be unverified and adjust the expectation accordingly.

## Canonical sources

- ISO/IEC 26514:2008, Systems and software engineering — Requirements for designers and developers of user documentation (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- NIST SP 800-53 Rev. 5, System and Information Integrity control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- ENISA, Risk Management Resources, https://www.enisa.europa.eu/topics/risk-management
- W3C, Technical Report publication conventions, https://www.w3.org/TR/