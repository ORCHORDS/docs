# email-testing-local-catchall

**Issue:** Application code that sends email — verification links, password resets, notification digests — is usually tested by either not testing it at all (mail silently goes nowhere in dev) or by sending to real addresses (leaking PII, burning reputation, flaky CI). The fix is a local catch-all SMTP server: every message the app emits is accepted and stored regardless of recipient, then inspected via a web UI or REST API. Teams using this pattern also want automated assertions in CI (did the reset email actually contain the link? is List-Unsubscribe present?) and a sane division between content assertions, which belong in CI, and pixel/rendering checks, which belong in a targeted client-matrix tool.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Local catch-all tooling choices

1. **Mailpit is the 2026 default.** A single Go binary (or the `axllent/mailpit` Docker image) that listens on SMTP :1025, catches every message to any address, and serves a web UI on :8025 plus a full REST API; it is actively maintained and has effectively superseded MailHog, which has been unmaintained for years.
2. **Mailcow catch-all for fuller-stack needs.** When tests must exercise real Dovecot/Postfix behavior — IMAP pickup, sieve filtering, full MIME fidelity — a local Mailcow instance with a catch-all mailbox gives a production-shaped mail server at the cost of docker-compose complexity and more RAM.
3. **Inbucket or SMTP4Dev for other stacks.** Inbucket offers a similar catch-all-plus-API model with per-mailbox views (useful when tests tag recipients like `user+test-123@local`), and smtp4dev is the .NET-ecosystem equivalent with a rules/scripting engine.
4. **Hosted sandboxes for shared-team review.** Mailtrap/Ethereal-style hosted sandboxes make sense when non-developers must eyeball campaigns, but they send mail off-machine and rate-limit; keep secrets-free local catch-alls for CI where everything stays on the runner.
5. **Fake transport mode still has a place.** For pure unit tests, a memory transport (Nodemailer `jsonTransport`, Django `locmem`, Laravel `log`) asserts without any socket — but it skips MIME generation realities, so keep at least one integration layer test that goes through a real SMTP conversation with Mailpit.

## Wiring dev and CI environments

1. **Point SMTP config at the catch-all via env.** `SMTP_HOST=mailpit`, `SMTP_PORT=1025`, no auth, no TLS — every environment (local, docker-compose, CI) differs only by hostname, so the app code never branches.
2. **Run Mailpit as a docker-compose service in dev.** One service entry (`axllent/mailpit`, ports 1025/8025, a volume if you want persistence across restarts) gives every developer an identical inbox at `localhost:8025`.
3. **Use Testcontainers in CI for lifecycle control.** The Testcontainers pattern spins up an ephemeral Mailpit per test run (or per suite), so tests start from a clean mailbox and the container dies with the job — no shared state between PR builds.
4. **For GitHub Actions, use a service container.** A `services: mailpit: image: axllent/mailpit` block exposes the container to job steps by hostname; add a health-check step that polls the web port before tests fire the first message.
5. **Add an `.mailer` subdomain if the app constructs URLs.** Set the app's mail domain to `mailpit.local`/`localhost` in test env so generated links (`https://app.test/reset?token=...`) are visibly fake if they ever leak into logs or screenshots.

## Asserting on sent mail

1. **Poll, do not sleep.** Sending is usually asynchronous (queue worker); poll `GET /api/v1/messages` with a bounded retry loop (e.g. 30 × 1s) until the expected message appears instead of a fixed sleep that is either flaky or slow.
2. **Query with the search API.** `GET /api/v1/search?query=to:user+test@local` narrows by recipient/subject before fetching the full message, which keeps assertions deterministic when other tests send mail concurrently.
3. **Fetch the parsed message for deep checks.** `GET /api/v1/message/{id}` returns parsed MIME parts, HTML, text, and headers — assert on the text part for token links (regex the one-time token out), and on HTML for template regression.
4. **Assert the headers that compliance cares about.** Every test of a bulk/notification template should assert `List-Unsubscribe` and `List-Unsubscribe-Post: List-Unsubscribe=One-Click` are present and well-formed, plus `Message-ID` uniqueness — these break silently in code review but loudly at Gmail.
5. **Verify recipient resolution, not just delivery.** Tests that send to `to` + `cc`/`bcc` combos should assert the recipient list captured by the catch-all matches intent, catching the classic BCC-leak-into-To bug before Gmail's complaint rate does.
6. **Clean state between tests.** `DELETE /api/v1/messages` in a `beforeEach` avoids cross-test contamination; without it, a passing test can pass for the wrong reason by matching the previous test's message.

## Rendering and client-matrix testing

1. **Use the built-in preview as the first rendering gate.** Mailpit's web UI renders the HTML part and flags broken/unsupported markup with its HTML-checker; developers catch most layout breakage right there without any external service.
2. **Keep pixel-perfect checks out of unit CI.** True client-matrix rendering (Outlook desktop's Word engine, Apple Mail, dark-mode Gmail) requires seed-based services (Email on Acid, Litmus, or headless-Chrome screenshot farms) — too slow and flaky to run per-commit; run them on a schedule or PR-label trigger instead.
3. **Dark mode is a content-adjacent assertion.** Dark-mode inversion breaks transparent PNG logos and hardcoded `color` styles; automated screenshot diffs of a dark-scheme render catch this cheaply with a single headless browser, without the full client matrix.
4. **Snapshot the HTML, not the screenshot.** A committed snapshot of the rendered HTML part (post-template, pre-send) diffed on PR review catches unintended template changes deterministically and reviews well — screenshots in PRs get rubber-stamped.
5. **Validate links as part of rendering checks.** Crawl all `href`/`img src` in the captured message and assert they resolve (200/302) in the test environment; broken tracking domains and dead CDN images are rendering bugs that content assertions never see.

## CI pipeline patterns

1. **One pipeline job, three assertion layers.** Order: unit tests with memory transport (fast), integration tests through Mailpit (content + headers), then a nightly/scheduled job for client-matrix screenshots — each layer failing independently keeps the signal clean.
2. **Fail on missing authentication-adjacent headers.** The Mailpit stage is the cheapest place to enforce repo-wide invariants: every message must have `Message-ID`, bulk templates must have working unsubscribe headers, and transactional templates must have the `Precedence: bulk` handling your ESP expects.
3. **Archive the mailbox as a build artifact.** Upload Mailpit's data (or an API dump of messages) on failure; a red build with the actual rendered emails attached turns a flaky-mail mystery into a five-minute fix.
4. **Never let CI assert on real DNS or real recipients.** A test that "verifies" by emailing a human inbox couples CI to the network and reputation; the catch-all exists precisely so the pipeline is hermetic — treat any `@gmail.com` in test config as a defect.
5. **Load-test the mail path separately.** Catch-all servers store everything in memory/disk; if a perf test sends 100k messages, cap Mailpit's retention (`--max-messages`) or point the load test at a discard transport, or the CI runner OOMs on mail volume.
