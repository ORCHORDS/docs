# risk-based-deployment-gating

**Issue:** Risk-based deployment gating — auto-routing changes to the right validation path based on risk level (the 2026 predictive-CI/CD pattern)
**Date:** 2026-08-13
**Status:** documented

## Symptom
Every change goes through the same pipeline: a 1-line README fix
waits behind the same 45-minute integration suite, static-analysis
gates, manual CAB approval, and progressive rollout as a core
payment-schema migration. Developers hate the friction, so they
batch changes into huge weekly deploys — which are now genuinely
risky and do need all the gates. The safe path made the system less
safe.

## Root cause
**Treating every change as high-risk wastes effort on safe changes
and under-protects the genuinely dangerous ones.** The 2026 pattern
is risk-based gating: classify each change, then auto-route low-risk
changes to a fast path, medium-risk to standard validation, and
high-risk to full review + progressive delivery.

**Source:** Medium — "The 2026 CI/CD Revolution: Predictive,
Automated & Kubernetes-Native" (selective/contextual automation);
Harness — Kubernetes CI/CD Best Practices (progressive delivery
gating).

## The "risk classifier" pattern

Classify a change from its diff before choosing a path:

```ts
interface RiskAssessment {
  level: 'low' | 'medium' | 'high';
  reasons: string[];
  path: 'auto' | 'standard' | 'gated';
}

function assessRisk(diff: Diff, changedFiles: string[]): RiskAssessment {
  const reasons: string[] = [];

  // High-risk signals
  if (changedFiles.some(f => f.includes('migrations/'))) {
    reasons.push('touches database schema');
  }
  if (changedFiles.some(f => f.includes('terraform/') || f.endsWith('.tf'))) {
    reasons.push('modifies infrastructure');
  }
  if (diff.touchesFilesMatching(/payment|billing|checkout/i)) {
    reasons.push('touches payment-critical code');
  }
  if (diff.linesChanged > 500) {
    reasons.push(`large diff (${diff.linesChanged} lines)`);
  }

  // Low-risk signals
  const onlyDocs = changedFiles.every(f =>
    /\.(md|txt)$/.test(f) || f.startsWith('docs/')
  );
  const onlyComments = diff.isOnlyComments();

  if (reasons.length >= 2) return { level: 'high', reasons, path: 'gated' };
  if (reasons.length === 1) return { level: 'medium', reasons, path: 'standard' };
  if (onlyDocs || onlyComments) return { level: 'low', reasons: ['docs/comments only'], path: 'auto' };
  return { level: 'medium', reasons: ['unclassified'], path: 'standard' };
}
```

The classifier runs as the first CI step and writes the chosen path
to the pipeline output.

## The "three paths" pattern

Route to a different job graph based on the assessment:

```yaml
# GitHub Actions — choose path from risk assessment
jobs:
  classify:
    outputs:
      path: ${{ steps.risk.outputs.path }}
    steps:
      - id: risk
        run: ./scripts/assess-risk.sh >> $GITHUB_OUTPUT

  auto:        # low-risk: build + unit test, deploy immediately
    needs: classify
    if: needs.classify.outputs.path == 'auto'
    steps:
      - run: pnpm test
      - run: ./scripts/deploy.sh --env prod --strategy rolling

  standard:    # medium-risk: + integration tests, deploy to staging then prod
    needs: classify
    if: needs.classify.outputs.path == 'standard'
    steps:
      - run: pnpm test && pnpm test:integration
      - run: ./scripts/deploy.sh --env staging
      - run: ./scripts/smoke.sh --env staging
      - run: ./scripts/deploy.sh --env prod --strategy rolling

  gated:       # high-risk: + review approval, progressive delivery, auto-rollback
    needs: classify
    if: needs.classify.outputs.path == 'gated'
    environment: 'prod-approval'   # manual approve in GitHub Environments
    steps:
      - run: pnpm test && pnpm test:integration && pnpm test:e2e
      - run: ./scripts/security-scan.sh
      - run: ./scripts/deploy.sh --env prod --strategy canary --max-pct 10
      - run: ./scripts/watch-metrics.sh --window 15m --rollback-on-regression
```

Low-risk changes ship in 3 minutes; high-risk changes get the full
treatment they actually need.

## The "auto-deploy guardrails" pattern

Auto-deploy is safe only with hard guardrails. Enforce all of:

```bash
# Guardrails checked before any auto-deploy runs
./scripts/check-guardrails.sh || exit 1
```

```bash
#!/usr/bin/env bash
# check-guardrails.sh
set -euo pipefail

# 1. Main branch only — no auto-deploy from feature branches
[ "$(git rev-parse --abbrev-ref HEAD)" = "main" ] || \
  { echo "auto-deploy only on main"; exit 1; }

# 2. All required checks green
gh api repos/:owner/:repo/commits/$CI_SHA/check-runs \
  --jq '.check_runs[].conclusion' | \
  grep -qv "success" && { echo "not all checks green"; exit 1; }

# 3. Below deploy-freeze window
./scripts/check-freeze-window.sh || exit 1

# 4. Previous deploy succeeded (don't stack on a broken prod)
./scripts/last-deploy-healthy.sh || exit 1

# 5. Diff size under auto-deploy cap
[ "$(git diff --numstat HEAD~1 | awk '{s+=$1+$2} END{print s}')" -lt 50 ] || \
  { echo "diff too large for auto-deploy, route to standard"; exit 1; }
```

If any guardrail fails, the change is routed to `standard` instead.

## The "metric-based auto-rollback" pattern

For high-risk progressive delivery, rollback is automatic on
regression — no human needed:

```bash
# Watch SLO metrics during the canary; rollback if they regress
./scripts/watch-metrics.sh \
  --window 15m \
  --metric error_rate \
  --threshold 'green_error_rate > blue_error_rate * 1.5' \
  --metric p99_latency \
  --threshold 'green_p99 > blue_p99 * 1.3' \
  --on-regression './scripts/rollback.sh --to blue'
```

This is the 2026 "automated rollback is table stakes" pattern from
the progressive-delivery search results.

## The "audit the classification" pattern

Record every risk decision so you can tune the classifier:

```bash
# Log the assessment with the build
echo "{
  \"sha\": \"$CI_SHA\",
  \"path\": \"$(cat risk-path.txt)\",
  \"reasons\": \"$(cat risk-reasons.txt)\",
  \"files\": $(git diff --name-only HEAD~1 | jq -R . | jq -s .)
}" >> /var/log/deploy-risk.jsonl
```

Review monthly: are high-risk changes getting through? Are low-risk
ones wrongly gated? Adjust the classifier thresholds based on real
incidents.

## Verification
- **Test:** A docs-only change is classified `low` and takes the
  `auto` path; verify it deploys without manual approval.
- **Test:** A migration file change is classified `high` and
  requires the `prod-approval` environment.
- **Test:** Each guardrail, when violated, routes to `standard`.
- **Audit:** Monthly review of the risk-decision log; tune
  thresholds based on any incident that bypassed or was over-gated.

## Gotchas
- **The "one pipeline for all" anti-pattern.** Forcing every change
  through the heaviest path causes batching, which makes deploys
  genuinely riskier. Route by risk.
- **The "auto-deploy without guardrails" anti-pattern.** Auto-deploy
  with no freeze-window, no green-check, or no diff-size check will
  ship a broken or oversized change to prod. Guardrails are mandatory.
- **The "frozen classifier" anti-pattern.** Risk rules set once and
  never revisited drift from reality. Review the decision log monthly.
- **The "high-risk with no auto-rollback" anti-pattern.** A gated
  deploy that still requires a human to notice a regression is not
  safe — pair progressive delivery with metric-based auto-rollback.
- **The "trust the classifier blindly" anti-pattern.** The classifier
  is heuristic. Always allow a human to override to a higher path.

## Related
- `progressive-delivery-2026.md`
- `deployment-approval-workflow.md`
- `deployment-freeze-policy.md`
- `environment-promotion-gates.md`
- `canary-deployments.md`
- `cab-change-management.md`
- `trunk-based-development.md`
