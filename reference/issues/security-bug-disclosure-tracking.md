# security-bug-disclosure-tracking

**Issue:** A security bug is not just a bug with a scarier label: from the moment it is reported, the clock on coordinated public disclosure starts running, multiple external parties (the reporter, downstream users, library maintainers, sometimes a CERT or CNA) have stakes and deadlines, and mishandling the tracking leaks exploitable details before a patch ships or burns a researcher who trusted you. Teams that treat security reports as ordinary issues fail predictably — details exposed in a public tracker, embargo dates forgotten, a CVE reserved but never populated, fixes shipped before affected versions were inventoried. Record CVE volume (2025 tracked on pace for well over 20,000 entries) makes manual, memory-based handling untenable. A disclosure-tracking discipline — private issue workflow, dated milestones, and multi-party coordination — is the difference between a coordinated release and an incident on top of an incident.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The private issue workflow

1. **Security reports never enter the public tracker.** Reports arrive via a security.txt file, a security@ inbox, or a private vulnerability-reporting channel (GitHub private vulnerability reporting, for example). The moment a security bug is filed as a normal issue, its details, reproduction, and often the affected code paths are public to anyone watching the repo — the single most common self-inflicted leak.
2. **Use a restricted tracker or private security-issue type.** GitHub Security Advisories, GitLab confidential issues, or a dedicated access-controlled project give the collaboration benefits of issue tracking (assignments, comments, state) with visibility limited to the response team. The public tracker gets, at most, a non-disclosing placeholder linked after publication.
3. **Fix privately, release and disclose together.** The coordinated sequence is: fix on a private branch or restricted-access fork, prepare the advisory and patched release simultaneously, then publish advisory, release, and public issue in one action. Publishing the fix before the advisory — or announcing before the patch is live — each creates an exploit window.
4. **Mirror the fix into the public history without leaking.** When the private fix merges publicly, keep the commit message non-descriptive until disclosure, or use a separate published advisory with credit. Repos that push descriptive security commit messages before the release tag exists hand attackers a diff and a head start.

## Disclosure milestones to track per issue #<number>. **Report received and acknowledged.** Record the date the reporter was acknowledged, with a promised response cadence. 2025 research on vulnerability disclosure (ACM; arXiv 2506.14323) shows disclosure fails most often at notification mechanics — messages going to stale contacts or being ignored — so acknowledgment is a real milestone, not a formality.
2. **Validation and severity scoring.** Confirm reproduction, assign CVSS, and decide exploitability. This gates everything downstream: an unexploitable informational issue can follow a lightweight path; a critical RCE triggers the full coordination machine.
3. **Fix ready and affected versions enumerated.** The inventory of affected versions and configurations is what turns a patch into an advisory. Track it as an explicit checklist item — advisories delayed for days after code completion are almost always waiting on this.
4. **CVE or identifier reserved and populated.** Reserve through your CNA (GitHub, for hosted projects, is one) or MITRE, and track the gap between reservation and population — a reserved-but-empty CVE blocks downstream consumers' scanners and dependency tools from matching your fix.
5. **Coordinated disclosure date agreed.** With an external reporter, agree the date explicitly; Project Zero's well-known policy is a fixed 90-day clock with the deadline published, which works because it is a policy stated up front rather than a deadline invented late. Whatever the number, track it as a date field, not a vibe.
6. **Published, credited, and post-published review scheduled.** Advisory live, reporter credited (if they wish), users notified through the release channel, and a short internal review of the handling booked — the same blameless-postmortem treatment as any incident.

## Multi-party coordination

1. **Identify every party before setting the date.** FIRST's multi-party coordination guidance exists because modern vulnerabilities span a chain: your library, three frameworks built on it, and hundreds of deployers. If downstream maintainers need the fix early to prepare theirs, the embargo must cover them — which means a private pre-disclosure channel with identified contacts, not a mass email at release time.
2. **Share early, minimal, and encrypted with named parties.** Give downstream integrators the fix and a short technical description under embargo, not the full exploit. Trusted-channel discipline from current CVD practice: known contacts, encrypted where practical, and a named human on each end.
3. **Tier the pre-notification list.** Critical, widely-embedded issues justify notifying major deployers (cloud providers, distros) days ahead; low-severity local issues rarely justify any pre-notification. Write the tiering rules down in the disclosure policy so each case is not relitigated.
4. **Handle unresponsive or hostile reporters per policy.** If a reporter goes silent or threatens immediate publication, the fallback is documented: proceed with the fix, set a final disclosure date, and publish. A policy decided calmly in advance beats one improvised under pressure.

## Publishing and maintaining the record

1. **Publish one canonical advisory with the full history.** Affected versions, patched versions, CVSS and vector, CWE, credits, mitigation for users who cannot upgrade immediately, and the timeline (reported, fixed, disclosed). This is the durable artifact scanners and auditors read.
2. **Keep a public disclosure policy so reporters know the rules before they report.** A security.txt file, scope statement, safe-harbor language for researchers, and expected timelines — CISA's coordinated vulnerability disclosure program and GCVE best-practice guidance both treat a published policy as the foundation of handling.
3. **Never amend quietly.** If the advisory turns out wrong — severity mis-scored, another affected version found — update with a visible changelog and re-notify. Silent edits destroy the trust the whole system runs on.
4. **Audit the pipeline quarterly.** Check for reserved-but-unpopulated CVEs, advisories missing affected-version ranges, and issues whose disclosure date passed without action. These are the accumulation points of disclosure debt, and they only surface if someone looks for them on purpose.
