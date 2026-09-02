# OpenSSF Scorecard Governance

## Purpose

The OpenSSF Scorecard is an automated tool that evaluates a set of security practices for open source projects and produces a score from 0 to 10. Scorecard checks include: code review, branch protection, dependency update tool, SAST, fuzzing, license, signed releases, security policy, dangerous workflow, token permissions, pinned dependencies, and others. This article governs the application of OpenSSF Scorecard so a project can assess and improve its security posture using the scorecard checks.

## Scope

The Scorecard applies to open source projects hosted on GitHub (with related support for other platforms). Within this knowledge base, the article covers the scorecard checks, the scoring methodology, the improvement workflow, and the integration of scorecard into the project's CI. It does not certify the project; the scorecard is a heuristic tool that surfaces practices the project should consider.

## Workflow

1. Run the Scorecard against the project's repository. The Scorecard produces a JSON output with the per-check scores and the underlying evidence.
2. Review the per-check results. Each check has a defined purpose and evidence source.
3. Prioritize improvements based on the score and the project's risk profile. Checks with low scores and high impact (e.g., branch protection, dangerous workflow, signed releases) take precedence.
4. Implement the improvements:
   - Branch protection: enable required reviews, status checks, and restrictions on the default branch.
   - Dependency update tool: enable DepDependabot or Renovate to keep dependencies current.
   - Security policy: write and publish SECURITY.md.
   - Pinned dependencies: pin GitHub Actions and container images by hash.
   - Signed releases: sign releases using sigstore cosign or GPG.
   - Token permissions: set the GITHUB_TOKEN to read-only by default.
   - Dangerous workflow: avoid patterns that allow code injection from untrusted input.
6. Re-run the scorecard periodically and after each material change. Track the trend.
7. Integrate the scorecard into CI to alert on regressions.

## Controls and evidence

Scorecard evidence is the JSON output of each run. The scorecard is reproducible; the same checks on the same repository at the same time produce the same output. The trend over time is the evidence of improvement.

## Validation

Validation should confirm the scorecard runs against the project's repository, the results are reviewed and acted on, the trends show improvement, and the scorecard is integrated into CI for regression detection. Periodic review confirms the trend.

## Failure correction

Common failure modes: the scorecard is run once and the result ignored (correct: review the per-check results and plan improvements); improvements are not prioritized (correct: prioritize by score and risk); the scorecard is not re-run (correct: re-run on material changes and on a planned cadence); the scorecard checks are taken as definitive (correct: treat the scorecard as a heuristic and consider the project's context).

## Limitations

The scorecard is a heuristic; it does not certify security. The checks measure whether certain practices are present, not whether they are implemented correctly. A high scorecard score does not guarantee security. The scorecard does not cover every security concern (e.g., AI-specific risks, runtime threats).

## Scope note

This article summarizes project-neutral platform use of the OpenSSF Scorecard. It does not assert any specific project's conformance or claim any certification outcome.

## Canonical sources

- OpenSSF Scorecard: https://scorecard.dev/
- OpenSSF Scorecard Checks: https://scorecard.dev/viewer/?uri=github.com/ossf/scorecard