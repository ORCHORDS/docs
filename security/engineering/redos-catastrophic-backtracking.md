# redos-catastrophic-backtracking

**Issue:** A regex used for validation, routing, or parsing contains a pattern with nested quantifiers or overlapping alternation branches. On crafted input the backtracking engine explores exponentially many parse paths — the OWASP example `^(a+)+$` takes 65,536 paths for 17 `a` characters, doubling with each added character. A single request with `aaaaaaaaaaaaaaaaaaaaaaaa!` then blocks the event loop (Node.js/V8 Irregexp), worker, WAF, or database regex function for minutes. A 2025 ACM systematization ranked ReDoS among the most common server-side vulnerabilities (fourth), and 2025 CVEs keep landing under CWE-1333 (octokit CVE-2025-25289; brace-expansion SNYK-JS-BRACEEXPANSION-9789073; multiple "O(N²) backtracking blocks the Node.js event loop" advisories). Famous outages include Stack Overflow (2016) and Cloudflare (2019).

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What makes a pattern "evil"

1. **Nested quantifiers.** A quantified group that contains another quantified expression — `(a+)+`, `([a-zA-Z]+)*`, `(a|aa)+` — gives the engine combinatorially many ways to partition a matching prefix, all of which are explored when the overall match fails.
2. **Overlapping alternation branches.** Branches where one alternative is a prefix of another (`(a|aa)+`, `(a|a?)+`) create ambiguity the engine resolves by backtracking through every combination.
3. **The trigger input.** A long run of the repeated character followed by a non-matching terminator (`aaaaaaaaaaaaaaaaaaaaaaaa!`) forces total failure after maximal backtracking; attackers need only know the shape of the pattern, and client-side validation leaks it since attackers assume the server reuses the same regex.
4. **Regex injection.** When user input is interpolated into the pattern itself (e.g., `new Regex(username)`), the attacker supplies the evil structure directly; treat any pattern built from request data as untrusted code.
5. **Blast radius beyond the app server.** The same pattern shapes hang browser tabs, WAF inspection engines, database regex functions, and log-parsing pipelines — a ReDoS in a middleware dependency (the octokit/brace-expansion case) freezes every service that routes traffic through it.

## Runtime realities in 2025-2026 stacks

1. **V8/Irregexp (Node.js, Chromium) backtracks.** Irregexp applies JIT heuristics and a modest backtracking budget, but worst-case behavior remains quadratic-to-exponential; the dominant 2025 CVE pattern is "O(N²) backtracking blocks the Node.js event loop" — one request freezes the whole process because JS is single-threaded.
2. **Linear-time engines exist and are drop-in for most patterns.** RE2 (and the `re2` npm/Go/Rust bindings, Rust's `regex` crate) guarantee linear time by forgoing backtracking; the trade-off is losing backreferences and lookahead/lookbehind, so audit patterns before swapping engines.
3. **Safer pattern syntax.** Where the engine supports it, atomic groups `(?>...)` and possessive quantifiers (`a*+`, `a++`) cut backtracking dead ends; these have landed in modern engines including PCRE2, Java, .NET, and increasingly JavaScript toolchains.
4. **Upstream CVEs arrive through dependencies.** Most real-world ReDoS in 2025 came from transitive dependencies (path-to-regexp-style routers, octokit, brace-expansion), so SBOM-driven patching — not just first-party code review — is the operative control.

## Defenses

1. **Ban nested quantifiers and overlapping alternation at review time.** Lint first-party patterns with `safe-regex` / `vuln-regex-detector` style checkers in CI so an evil regex fails the build instead of production.
2. **Cap input length before matching.** Most evil patterns need a long homogeneous run; rejecting or truncating oversized inputs (say >1 KB for validators) collapses the exponent cheaply.
3. **Use a linear-time engine for untrusted input.** Route user-supplied strings through RE2/Rust-regex bindings; keep the fancy backreference patterns for trusted, internal data only.
4. **Apply timeouts/match limits where the runtime offers them.** Wrap matches in a job with a deadline (worker thread + timeout in Node, `REGEXP_TIME_LIMIT`-style settings in databases, .NET `matchTimeout`); on timeout, fail closed and log.
5. **Never build patterns from request data.** Whitelist the regex sources; if user-configurable matching is a product requirement, compile their pattern with the linear engine and reject unsupported constructs with a clear error.
6. **Patch the supply chain.** Track CWE-1333 advisories against dependencies (Snyk/GitHub Dependabot both tag ReDoS), and pin patched versions promptly — these are cheap upgrades with no API churn.
7. **Test with adversarial input.** Add a fuzz case to the suite: for every validator regex, feed 10-1000 repetitions of its quantified character followed by a non-match, and assert the match completes within a time budget.

## Sources

1. **OWASP — Regular expression Denial of Service (ReDoS).** https://owasp.org/www-community/attacks/Regular_expression_Denial_of_Service_-_ReDoS (evil-pattern anatomy, exponential example, prevention).
2. **SoK: Literature & Engineering Review of Regular Expression DoS (ACM CSUR, 2025).** https://dl.acm.org/doi/full/10.1145/3708821.3733912 / https://arxiv.org/html/2406.11618v3 (prevalence ranking, Stack Overflow/Cloudflare outages).
3. **2025 CVEs under CWE-1333.** GHSA-xx4v-prfh-6cgc (octokit CVE-2025-25289), SNYK-JS-BRACEEXPANSION-9789073, Feedly CWE-1333 tracker (V8 O(N²) event-loop blocking pattern).
