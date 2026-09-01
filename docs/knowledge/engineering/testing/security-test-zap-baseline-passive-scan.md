# Security Test Zap Baseline Passive Scan

A passive scan observes traffic; it does not attack. ZAP's baseline scan runs ZAP against
a running application in passive mode: it spiders the application, records the requests
and responses, and analyses them for security weaknesses that are visible in the traffic
itself — missing security headers, cookies without protective flags, mixed content,
outdated library signatures in response bodies. Because it never sends an attack payload,
it is fast, deterministic, and safe to run against a production mirror. It is also
shallow: it finds only what is visible in passive observation. The baseline scan's value
is as the floor of a security pipeline — the cheap, always-on check that catches
regressions in configuration — not as a substitute for active scanning.

## Scope

Covers the integration of OWASP ZAP's baseline scan into an automated security test
pipeline: when passive scanning is appropriate, how the baseline scan is configured and
run, how its findings are triaged and gated, and what it can and cannot detect. Applies
to CI pipelines that build and deploy the application before scanning it. Does not cover
active scanning, manual penetration testing, or the full ZAP API scan.

## Workflow or implementation guidance

1. **Run the baseline scan against a running deployment.** The baseline scan needs a live
   target. In CI this is typically a freshly deployed staging or review environment; in
   a container pipeline the target is the application container started as a service.
   The scan is not a static analysis of source code; it observes the application's
   responses.
2. **Start with the packaged baseline invocation.** ZAP's Docker image provides a
   `zap-baseline.py` entry point that runs the passive scan, reports findings, and exits
   non-zero if any rule above a configured threshold fires:

```bash
docker run -t owasp/zap2docker-stable zap-baseline.py \
  -t https://staging.example.com \
  -c zap-rules.conf \
  -r zap-report.html
```

The `-c` file carries per-rule configuration: which rules fail the build, which are
warnings, which are ignored.

3. **Configure the rule set deliberately.** The baseline scan ships with a default set of
   passive rules. Three categories matter for CI gating:
   - **Fail**: rules that indicate a genuine, actionable weakness — missing
     `Strict-Transport-Security`, missing `Content-Security-Policy`, session cookies
     without `HttpOnly` or `Secure`.
   - **Warn**: rules that may be acceptable but deserve review — verbose server headers,
     missing `X-Content-Type-Options` on endpoints that do not need it.
   - **Ignore**: rules that are noise for this application — for example, cache-control
     directives on deliberately cacheable public assets.
   Every `Ignore` entry carries a rationale; an ignore list without rationale becomes a
   dumping ground.
4. **Authenticate the spider where the application requires it.** An unauthenticated
   baseline scan sees only the public surface. To scan the authenticated surface,
   configure ZAP's authentication (form-based or token-based) so the spider can reach
   the logged-in pages. Without this, the scan reports on a fraction of the application
   and the team believes it is covered.
5. **Treat the report as the artefact, not the exit code.** The exit code is the gate; the
   HTML report is the evidence. Persist the report for each CI run so a rule that moves
   from *pass* to *warn* is visible across releases even when the gate did not fail.
6. **Gate on the fail set only.** A gate that fails on warnings produces a pipeline that
   is always red and eventually ignored. Gate on the rules that have been explicitly
   classified as fail; move rules into that category as the team's tolerance tightens,
   not all at once.
7. **Triage the findings into the normal defect workflow.** A baseline finding is a
   defect with an owner and a deadline, like any other test failure. Findings that live
   only in a report nobody reads are findings that never get fixed.
8. **Run the baseline scan on a schedule as well as on change.** Configuration drift — a
   header removed by an infrastructure change, a reverse proxy added without the
   security headers forwarded — is invisible to a scan that runs only on application
   changes. A nightly or weekly scan catches drift.
9. **Keep the ZAP version current.** Passive rules improve between ZAP releases; a scan
   pinned to an old version reports against an old rule set. Pin to a specific version
   for reproducibility, and bump it deliberately with the release notes reviewed.

## Controls

- The rules configuration file is committed to the repository; every `Ignore` entry has a
  written rationale and an owner.
- The baseline scan runs in CI on every change to the application and on a schedule
  against the deployed environment.
- The scan is authenticated where the application has an authenticated surface; the
  authentication configuration is maintained with the application's auth changes.
- The HTML report is persisted per run and retained for the agreed period.
- ZAP's version is pinned and bumped deliberately, with the release notes' rule changes
  reviewed at each bump.

## Validation evidence

- Removing a security header from the application's configuration causes the baseline
  scan to fail the CI run; the rehearsal proves the gate is wired to the right rule.
- Adding an ignore entry without rationale is rejected in code review; the ignore file's
  rationale column is populated.
- The authenticated spider reaches the logged-in surface; the report includes URLs only
  visible after authentication.
- A scheduled scan catches a configuration drift introduced by an infrastructure change
  that did not touch the application code.

## Failure modes and correction

- *Baseline scan always green.* The rule set is too permissive or the spider reaches
  almost nothing. Check the report's crawled URL count; configure authentication.
- *Baseline scan always red.* Warnings are gating. Move rules from fail to warn until the
  pipeline is green, then tighten deliberately.
- *Ignore list grows without rationale.* Require the rationale; review the list at every
  release and remove entries that no longer apply.
- *Scan runs against a stale environment.* The target URL must point at the freshly
  deployed candidate, not at a long-lived staging environment that has drifted.
- *Report not persisted.* Persist it; a rule that moves between severities across
  releases is only visible with history.
- *ZAP version unpinned.* Pin it; different versions report different rule sets and the
  gate's meaning shifts silently.

## Limitations

- Passive scanning observes traffic; it does not test for vulnerabilities that require
  an attack payload — SQL injection, cross-site scripting, authentication bypass. Those
  need active scanning or manual testing.
- The scan's coverage is bounded by what the spider reaches. Pages behind complex
  authentication, JavaScript-driven navigation, or undocumented endpoints may not be
  visited.
- Baseline findings are predominantly configuration-level. They say nothing about
  business-logic flaws, access control errors, or data-handling mistakes.
- Running against a production mirror requires that the mirror be faithful. A staging
  environment with different headers, different proxies, or different feature flags
  produces findings that do not apply to production.
- The scan is a point-in-time observation. A new endpoint added after the scan ships
  without being scanned is a gap until the next run.

## Canonical sources

- OWASP ZAP, *Baseline scan documentation* (invocation, rule configuration, and report
  format): https://www.zaproxy.org/docs/docker/baseline-scan/
- OWASP ZAP, *ZAP documentation* (passive scanning rules, spider configuration, and
  authentication setup): https://www.zaproxy.org/docs/
- OWASP, *OWASP community resources* (the broader testing guidance the ZAP rules
  encode): https://owasp.org/www-community/
