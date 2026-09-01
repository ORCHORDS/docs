# Support Knowledge Article Deprecation Migration Notice

## Scope

This article governs how the support knowledge base retires an article that is no longer accurate or relevant, and how it directs readers who relied on the retired article to the replacement. It applies to every knowledge article in the support corpus regardless of audience (customer-facing, partner-facing, internal agent runbook). It does not apply to short-lived operational notices such as incident updates or status messages, which use a different lifecycle. The discipline follows the content maintenance principles codified in ISO 26514 for user documentation and ISO 26515 for developer documentation, which together describe how documentation evolves with the product it describes.

The decision to deprecate an article is reached through a documented review. Reviewers weigh accuracy (does the article still describe current behaviour), relevance (is the underlying topic still supported), and reach (how many readers are still arriving at the article). The outcome of the review is either no action, a refresh in place, or a deprecation with migration. This article focuses on the third outcome.

## Workflow or implementation guidance

The deprecation workflow begins with a proposal. Anyone in the support or product organisation may propose a deprecation; the proposal records the article identifier, the proposed replacement, the reason, and the date. The proposal enters a queue reviewed by the knowledge base owner, who confirms the replacement is in place and fit for purpose. Once confirmed, the original article is moved into a "deprecated" state and a migration banner is inserted at the top of the article.

The migration banner has a defined structure. It states that the article is retired, names the replacement article by title and link, gives the effective date of the redirect, and explains what a reader should do if the replacement does not solve their problem. The banner never silently disappears the original content; readers who arrived through an external link or a search engine can still read the body of the deprecated article for a defined window, typically six months for customer-facing content and one year for partner and agent content. The redirect itself is a permanent redirect where the platform supports it, so search engines and bookmarks converge on the replacement.

The replacement article must answer the same reader question that the deprecated article answered. If the reader question has changed, the deprecation is the wrong action; a refresh is needed instead. The knowledge base owner is responsible for confirming that the replacement article passes the same fitness checks that any new article passes: it is reviewed by a subject matter expert, it carries a version and effective date, and it is tagged with the topics that the deprecated article carried.

Search and analytics infrastructure is updated to reflect the deprecation. The deprecated article is removed from internal search indexes that prioritise live content. The deprecated article may remain in external search results for the duration of the redirect window, with the banner giving readers the replacement path. After the redirect window, the article body is removed from public surfaces but retained in the archival store for audit and dispute purposes.

## Controls

Controls are designed to prevent the most common failure mode: a deprecated article is referenced by another internal artifact, and the internal artifact keeps the old article alive long after the migration window closes. To prevent this, an automated sweep scans for inbound links to the deprecated article from other knowledge articles, agent macros, training material, and customer-facing email templates. Each link is migrated to the replacement, with a documented exception process for links that the sweep cannot resolve safely.

A second control prevents a deprecation from being applied without a verified replacement. The deprecation cannot enter the production system until the replacement article passes a content review and the reviewer's identifier is recorded in the audit log. This is enforced at the workflow level, not at the policy level, so a well-meaning editor cannot skip it.

A third control prevents customer-impacting redirects. Before the redirect is enabled, the organisation runs a small experiment that exercises the redirect path from a representative sample of inbound sources: search engine results, internal search, email templates, and chat references. The experiment records the time to reach the replacement article, the prominence of the migration banner, and the absence of broken links.

## Validation evidence

Validation evidence is collected at three points in the lifecycle. At deprecation time, the replacement article is published, the redirect is tested, the inbound-link sweep completes, and the banner is rendered in the production layout. During the redirect window, a periodic report counts visits to the deprecated article and compares it against the rate expected by the migration model. After the redirect window, the archival record is finalised: the body of the deprecated article is preserved with the deprecation date, the replacement identifier, and the editor identifier.

## Failure modes and correction

The most common failure is the silent retirement of an article that still receives significant traffic. The reader sees a broken link or a 404, and the support desk sees a related uptick in inbound contacts. The correction is the discipline of leaving the deprecated article body in place behind a banner for the full window, and of monitoring the traffic to the deprecated article. If the traffic is higher than expected, the migration may need more time, or the replacement may not be answering the original question.

The second most common failure is the deprecated article being referenced from a system that does not respect the redirect. The correction is the inbound-link sweep, and the exception process that handles the small set of systems that cannot be changed quickly. The exception process keeps a record of the referring system, the expected retirement date, and a named owner.

The third most common failure is the replacement article drifting over time. A deprecation records that, on a particular date, the replacement answered the original reader question. If the replacement drifts away from that question, the migration becomes a dead end. The correction is to keep the replacement article under the same review cadence as any other article.

## Limitations

The minimum-data approach assumes the knowledge platform supports the workflow. Not all platforms support a banner state, a redirect window, and an archival store. On platforms with weaker capabilities, the deprecation workflow degrades gracefully but with more manual effort. The organisation must confirm that its platform supports the minimum workflow before it commits to the discipline.

The approach also assumes the organisation can identify the inbound links reliably. Where the inbound link sources are not under organisational control (public forums, partner sites, social media bookmarks), the inbound-link sweep will understate the actual reach. The organisation should treat the sweep as a floor, not a ceiling.

## Canonical sources

- ISO/IEC 26514:2008, Systems and software engineering — Requirements for designers and developers of user documentation (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- ISO/IEC 26515:2018, Systems and software engineering — Developing information for (and with) users in a regulated environment (publisher and title only; ISO standards pages return access-controlled responses to automated clients).
- NIST SP 800-53 Rev. 5, Information and Document Management control family, https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
- W3C, Technical Report publication conventions, https://www.w3.org/TR/