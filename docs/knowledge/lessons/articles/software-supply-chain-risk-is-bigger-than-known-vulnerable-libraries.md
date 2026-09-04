# Software Supply Chain Risk Is Bigger Than Known Vulnerable Libraries

**Issue:** A team treats software-supply-chain security as a dependency-CVE scanning problem and therefore overlooks unmaintained transitive dependencies, build tools, runtimes, repositories, distribution paths, and update mechanisms.

**Date:** 2026-09-04
**Author:** ORCHORDS
**Status:** documented

## The lesson

OWASP Top 10:2025 A03 expands the older "vulnerable and outdated components" idea into Software Supply Chain Failures. The relevant attack surface includes the process of building, distributing, updating, and depending on software—not only whether a directly declared library has a known CVE.

## Engineering rule

- Inventory direct and transitive dependencies plus material runtimes, build tools, package sources, and delivery/update mechanisms.
- Track versions and support/maintenance status instead of relying only on vulnerability scanner findings.
- Treat unsupported or unmaintained components as supply-chain risk even when no current CVE is known.
- Monitor security advisories and vulnerability sources for the components actually used.
- Govern where dependencies and build inputs come from and how software artifacts move through build, distribution, and update paths.
- Verify that security updates can be tested and deployed through an owned process.

## Verification

- Compare the dependency inventory against lockfiles/resolved dependency output and identify untracked transitive components.
- Sample non-library components such as runtimes, build tools, or servers and verify version/support status is tracked.
- Trace a released artifact back through its approved build and dependency inputs.

## Official source

- OWASP Top 10:2025 A03 — Software Supply Chain Failures: https://owasp.org/Top10/2025/A03_2025-Software_Supply_Chain_Failures/
