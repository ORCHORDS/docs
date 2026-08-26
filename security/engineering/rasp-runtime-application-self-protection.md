# RASP — Runtime Application Self-Protection

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your WAF blocks known attack signatures at the network edge, but
sophisticated attacks bypass it — parameter manipulation that looks benign at
the HTTP layer but exploits application logic, or zero-day vulnerabilities
where no WAF rule exists yet. You need protection that understands your
application's runtime behavior, not just its HTTP surface.

## Context

Runtime Application Self-Protection (RASP) instruments your application from
within — an agent or library hooks into the runtime (JVM, CLR, Node.js,
Python interpreter) and monitors function calls, database queries, file
access, and outbound requests in real time. Unlike a WAF (which sees HTTP
traffic) or SAST (which sees source code), RASP sees the actual execution
context: the specific SQL query being built, the file path being opened, the
deserialization happening. This lets it detect and block attacks with near-
zero false positives because it knows whether a suspicious input actually
reaches a vulnerable code path.

## Top tools (2026)

| Tool | Languages | Deployment | Overhead | Best for |
|---|---|---|---|---|
| Contrast Protect | Java, .NET, Node, Python, Go, Ruby | In-process agent | 2-5% | Established commercial RASP, part of Contrast platform (IAST + RASP) |
| Datadog ASM | Java, .NET, Node, Python, Go, Ruby | APM agent extension | 1-3% | Teams already using Datadog APM — enable security on existing agents |
| Dynatrace App Security | Java, .NET, Node, Go, PHP | OneAgent extension | 2-4% | Teams already using Dynatrace — runtime vulnerability detection |
| Imperva RASP | Java, Node | In-process agent | 3-7% | Enterprise compliance requirements, API protection |
| OpenRASP (Baidu) | Java, PHP | Open-source agent | 3-8% | Open-source, self-hosted, customizable rules |

## How RASP works

1. **Instrumentation** — the RASP agent hooks into critical runtime APIs
   (JDBC, HTTP client, file I/O, deserialization, process execution).
2. **Context capture** — when a hooked function is called, RASP captures
   the call context: the input data, the calling function, the user session.
3. **Analysis** — RASP compares the operation against its security model.
   Example: a SQL query contains a string that originated from HTTP input
   and includes SQL syntax (tautology, UNION, comment) → SQLi detected.
4. **Action** — block the operation, throw an exception, log the event, or
   alert. Configurable per rule: monitor mode (log only) or protect mode
   (block).

## RASP vs. WAF vs. SAST vs. DAST

| Property | WAF | RASP | SAST | DAST |
|---|---|---|---|---|
| When | Request time | Runtime | Build time | Test time |
| Sees | HTTP traffic | Code execution | Source code | HTTP responses |
| False positives | Medium-high | Very low | High | Medium |
| Zero-day coverage | Low | High | None | Low |
| Performance cost | Network latency | 2-5% CPU | Build time | Test time |
| Deployment | Edge/proxy | In-process | CI pipeline | CI pipeline |

## Anti-patterns

- **RASP as a replacement for secure coding** — RASP is a safety net, not a
  substitute for parameterized queries, input validation, and output
  encoding.
- **Deploying in protect mode on day one** — start in monitor/detect mode.
  Analyze findings for 2-4 weeks before enabling blocking.
- **Ignoring performance budgets** — RASP adds 2-5% overhead. Profile your
  application with RASP enabled under load. If latency SLOs are tight, tune
  which hooks are active.
- **Running RASP without WAF** — they complement each other. WAF stops known
  patterns at the edge (cheap); RASP stops what gets through (expensive but
  precise).

## Gotchas

- **Language coverage gaps** — Java and .NET have the broadest RASP support.
  Go, Rust, and newer runtimes have limited or no RASP agent availability.
- **Framework compatibility** — RASP hooks into specific framework versions.
  Verify compatibility with your exact framework and version before
  deploying (e.g., Spring Boot 3.x, Express 5.x, Django 5.x).
- **Container and serverless** — RASP agents add startup time and memory.
  In serverless (Lambda, Workers), the cold start penalty may be
  unacceptable. Test cold start impact.
- **Agent updates** — RASP agents need updates for new vulnerability
  patterns. Automate agent updates in your CI/CD pipeline.
- **Datadog ASM requires APM** — you must be running Datadog APM tracing
  to enable ASM. It is not a standalone product.

## Verification

- Test with known exploit payloads (OWASP WebGoat, Juice Shop) and verify
  RASP detects and blocks them.
- Verify false positive rate against your application's normal traffic.
- Load test with RASP enabled and compare latency p50/p95/p99 against
  baseline.
- Test the failure mode: what happens when the RASP agent crashes? Verify
  fail-open vs. fail-closed behavior matches your policy.

## Related

- `documentation/categories/security/waf-rules-configuration.md`
- `documentation/categories/security/owasp-top-10-2025.md`
- `documentation/categories/security/agent-guardrails-2026.md`
- `documentation/categories/security/dast-automated-scanning.md`
- `documentation/categories/security/sql-injection-deep-dive.md`

## Source URLs (verified 2026-08-16)

- Best RASP/ADR tools 2026 — https://appsecsanta.com/rasp-tools
- What is RASP 2026 — https://appsecsanta.com/application-security/what-is-rasp
- RASP security (Contrast) — https://www.contrastsecurity.com/glossary/rasp-security
- Top RASP tools 2025 — https://accuknox.com/blog/rasp-tools
- Best RASP software — https://expertinsights.com/devsecops/the-top-runtime-application-self-protection-rasp-software
