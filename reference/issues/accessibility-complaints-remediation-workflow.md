# Accessibility Complaints and Remediation Workflow

- **Date**: 2026-08-22
- **Author**: example.com
- **Status**: production

## Symptom / Use-case

A user with a screen reader cannot complete checkout because an unlabeled icon button triggers the payment flow. They file a support ticket, tag it "accessibility," and it gets routed to tier-2 support with no engineering path. Six weeks later, nothing has changed and a follow-up complaint arrives from a different user citing the same barrier.

A separate pattern: a power user using keyboard-only navigation reports that a modal dialog does not trap focus — pressing Tab cycles out of the dialog and onto the background page. The report gets labeled "edge case" and closed without a fix.

Both failures expose the platform to legal risk: ADA Title III complaints and DOJ civil investigative demands have increased every year since the *Robles v. Domino's* circuit court ruling (9th Cir. 2019). The EU Web Accessibility Directive (Directive 2016/2102) mandates WCAG 2.1 AA for public-sector sites and many large private platforms. The European Accessibility Act (EAA, Directive 2019/882) took effect June 2025 and requires private-sector digital services in scope to meet EN 301 549 (which maps to WCAG 2.1 AA).

## Context

Accessibility complaints differ from ordinary bugs: they carry regulatory urgency, often require assistive technology (AT) reproduction environments, affect multiple disability categories simultaneously, and demand a formal audit trail to demonstrate good-faith remediation if a complaint escalates to a civil rights agency or court.

The workflow spans: user-facing intake → triage and categorization → AT reproduction → engineering fix → verification with AT tools → public acknowledgment. Tooling involves GitHub Issues (with custom labels and issue templates), automated WCAG scanning (axe-core in CI), manual screen reader testing (NVDA + Chrome, VoiceOver + Safari, JAWS + Edge), and a compliance log in D1.

Each confirmed accessibility defect must be classified against WCAG 2.1 / 2.2 success criteria: level A (must fix immediately), level AA (must fix within 30 days for EAA compliance), level AAA (best effort). This SLA structure is distinct from the general bug severity matrix.

## Intake Template and Routing

A dedicated GitHub Issue template captures the AT context upfront, preventing back-and-forth with the reporter.

```markdown
<!-- .github/ISSUE_TEMPLATE/accessibility-complaint.yml -->
name: Accessibility Complaint
description: Report a barrier for users with disabilities
labels: ["accessibility", "triage"]
body:
  - type: dropdown
    id: disability_category
    attributes:
      label: Disability category
      options:
        - Visual (screen reader, low vision, color blindness)
        - Motor (keyboard-only, switch access, voice control)
        - Cognitive (reading difficulty, attention, memory)
        - Auditory (deaf / hard of hearing)
        - Multiple
    validations:
      required: true
  - type: dropdown
    id: assistive_technology
    attributes:
      label: Assistive technology in use
      options:
        - NVDA + Chrome
        - JAWS + Edge
        - VoiceOver + Safari (macOS)
        - VoiceOver + Safari (iOS)
        - TalkBack + Chrome (Android)
        - Keyboard only (no screen reader)
        - Dragon NaturallySpeaking (voice control)
        - ZoomText / magnification
        - Other
  - type: input
    id: page_url
    attributes:
      label: Page URL or feature name
    validations:
      required: true
  - type: textarea
    id: barrier_description
    attributes:
      label: Describe the barrier
      placeholder: |
        What were you trying to do? What happened instead?
        Include the screen reader output or keyboard sequence if possible.
    validations:
      required: true
  - type: textarea
    id: wcag_criterion
    attributes:
      label: WCAG success criterion (if known)
      placeholder: "e.g. 1.1.1 Non-text Content (A), 2.1.1 Keyboard (A)"
```

A GitHub Actions workflow auto-labels and routes on issue creation:

```yaml
# .github/workflows/accessibility-intake.yml
name: Accessibility Issue Routing
on:
  issues:
    types: [opened]

jobs:
  route:
    if: contains(github.event.issue.labels.*.name, 'accessibility')
    runs-on: ubuntu-latest
    steps:
      - name: Assign to accessibility triage team
        uses: actions/github-script@v7
        with:
          script: |
            await github.rest.issues.addAssignees({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              assignees: ['a11y-triage-lead']
            });
            await github.rest.issues.createComment({
              owner: context.repo.owner,
              repo: context.repo.repo,
              issue_number: context.issue.number,
              body: `Thank you for this accessibility report. Our team will assess it within **2 business days** and respond here with a WCAG classification and target remediation date. If this is a critical blocker (you cannot complete a core task), reply with \`/critical\` and we will escalate immediately.`
            });
```

## WCAG Automated Scanning in CI

Integrate axe-core into the Playwright test suite to catch regressions automatically. Failures are reported as GitHub Check annotations.

```typescript
// tests/a11y/axe-scan.spec.ts
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const CRITICAL_PAGES = [
  { name: "Home", path: "/" },
  { name: "Checkout", path: "/checkout" },
  { name: "Account Settings", path: "/account/settings" },
  { name: "Login", path: "/auth/login" },
  { name: "Signup", path: "/auth/signup" },
];

for (const page of CRITICAL_PAGES) {
  test(`WCAG 2.1 AA — ${page.name}`, async ({ page: pwPage }) => {
    await pwPage.goto(page.path);
    // Wait for hydration / lazy-loaded content
    await pwPage.waitForLoadState("networkidle");

    const results = await new AxeBuilder({ page: pwPage })
      .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"])
      .analyze();

    // Attach violations as test attachment for CI artifact
    if (results.violations.length > 0) {
      const report = results.violations.map((v) => ({
        id: v.id,
        impact: v.impact,
        description: v.description,
        nodes: v.nodes.map((n) => n.target),
      }));
      await test.info().attach("axe-violations.json", {
        body: JSON.stringify(report, null, 2),
        contentType: "application/json",
      });
    }

    expect(
      results.violations.filter((v) => v.impact === "critical" || v.impact === "serious"),
      `Critical/serious WCAG violations found on ${page.name}`
    ).toHaveLength(0);
  });
}

// Keyboard navigation smoke test — focus trap in modal
test("Checkout modal focus trap", async ({ page }) => {
  await page.goto("/checkout");
  await page.click('[data-testid="open-payment-modal"]');
  // Modal should be open
  await expect(page.locator('[role="dialog"]')).toBeVisible();

  // Tab through all interactive elements — focus must stay inside dialog
  const dialog = page.locator('[role="dialog"]');
  for (let i = 0; i < 10; i++) {
    await page.keyboard.press("Tab");
    const focusedElement = await page.evaluate(() => document.activeElement?.closest('[role="dialog"]'));
    expect(focusedElement).not.toBeNull();
  }
});
```

## Remediation Tracking and Compliance Log

Every confirmed a11y defect is logged to D1 with WCAG criterion, SLA deadline, and resolution status. This log serves as evidence of good-faith remediation if a complaint escalates.

```typescript
// workers/a11y-compliance-log.ts
export interface A11yDefect {
  issueNumber: number;          // GitHub issue #
  wcagCriterion: string;        // e.g. "2.1.1"
  wcagLevel: "A" | "AA" | "AAA";
  impactedAt: string;           // page URL or component name
  disabilityCategory: string;
  reportedAt: number;           // Unix ms
  slaDeadlineDays: number;      // 0 for Level A (immediate), 30 for AA, 90 for AAA
  status: "open" | "in_progress" | "fixed" | "verified" | "wontfix";
  fixedAt?: number;
  verifiedAt?: number;
  verificationMethod?: string;  // "axe-core", "manual-nvda", "manual-voiceover"
}

export async function logA11yDefect(defect: A11yDefect, env: Env): Promise<void> {
  const deadline = defect.reportedAt + defect.slaDeadlineDays * 24 * 3600 * 1000;
  await env.DB.prepare(
    `INSERT INTO a11y_defects
       (issue_number, wcag_criterion, wcag_level, impacted_at, disability_category,
        reported_at, sla_deadline, status)
     VALUES (?,?,?,?,?,?,?,?)`
  ).bind(
    defect.issueNumber, defect.wcagCriterion, defect.wcagLevel,
    defect.impactedAt, defect.disabilityCategory,
    defect.reportedAt, deadline, defect.status
  ).run();
}

export async function getOverdueSlaDefects(env: Env): Promise<A11yDefect[]> {
  const now = Date.now();
  const rows = await env.DB.prepare(
    `SELECT * FROM a11y_defects
     WHERE status IN ('open','in_progress')
       AND sla_deadline < ?
     ORDER BY sla_deadline ASC`
  ).bind(now).all<A11yDefect>();
  return rows.results;
}

// Called from a daily cron Worker to alert on SLA breaches
export async function slaBreachAlert(env: Env): Promise<void> {
  const overdue = await getOverdueSlaDefects(env);
  if (overdue.length === 0) return;

  const message = overdue
    .map((d) => `Issue #${d.issueNumber} — WCAG ${d.wcagCriterion} (${d.wcagLevel}) — ${d.impactedAt}`)
    .join("\n");

  await fetch(env.SLACK_WEBHOOK_URL, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: `:rotating_light: *Accessibility SLA breach* — ${overdue.length} defect(s) overdue:\n${message}`,
    }),
  });
}
```

## Verification with Assistive Technology

Automated axe scans catch ~30–40 % of WCAG issues. Manual AT verification is required before marking a fix as `verified`. Maintain a testing matrix:

```markdown
## Manual AT Verification Checklist (per fix)

| Environment             | Tester   | Date | Outcome |
|-------------------------|----------|------|---------|
| NVDA 2024.x + Chrome    | [name]   |      |         |
| JAWS 2024 + Edge        | [name]   |      |         |
| VoiceOver + Safari macOS| [name]   |      |         |
| VoiceOver + Safari iOS  | [name]   |      |         |
| TalkBack + Chrome Android| [name]  |      |         |
| Keyboard-only (Chrome)  | [name]   |      |         |

### Test scenarios:
1. Can the user complete the full task (e.g., checkout) without a mouse?
2. Are all interactive elements reachable via Tab and operable via Enter/Space?
3. Does the screen reader announce the element's role, name, and state correctly?
4. Are error messages programmatically associated with their fields (aria-describedby)?
5. Are dynamic content updates announced (aria-live regions)?
```

When closing a GitHub issue as fixed, add a structured resolution comment:

```markdown
## Resolution

**WCAG criterion**: 2.1.1 Keyboard (Level A)
**Fix**: Added `tabindex="0"` and `onkeydown` handler to the payment-confirm button;
         replaced `<div>` with semantic `<button>` element.
**Verification**: axe-core CI scan passes. Manual NVDA + Chrome test by @a11y-reviewer on 2026-08-20.
**Deployed**: v3.14.2 (2026-08-21)
**Compliance log updated**: a11y_defects row #487 set to `verified`.
```

## Anti-patterns

- **Closing accessibility reports as "won't fix" without a WCAG-level justification** — this is legal exposure; EAA and ADA do not recognize "low priority" as a defense. If you genuinely cannot fix it, document a conformance exception with an alternative access route.
- **Relying solely on axe-core** — automated tools miss focus-management bugs, meaningful sequence order issues (WCAG 1.3.2), and complex ARIA widget interactions. Manual screen-reader testing is not optional.
- **Using `aria-label` to paper over non-semantic HTML** — adding `aria-label="submit"` to a `<div>` with an `onclick` still fails keyboard and switch-access users because divs do not have native keyboard interaction. Fix the element type, not just the label.
- **Adding `tabindex="-1"` to visible interactive elements** — this removes them from the keyboard focus order while leaving them visually present, creating a keyboard trap for users who cannot use a mouse.
- **Treating color contrast as purely cosmetic** — WCAG 1.4.3 (contrast ratio ≥ 4.5:1 for normal text) is a Level AA requirement under EAA. Failing it is a compliance defect, not a design preference.
- **Not training support agents to recognize AT-related tickets** — a ticket saying "the button doesn't work with my screen reader" arriving in the general queue and being answered with "try a different browser" is a lost signal and a frustrated user.

## Gotchas

- axe-core `withTags(["wcag2a", "wcag2aa"])` does not test WCAG 2.2 criteria (e.g., 2.4.11 Focus Not Obscured); add `"wcag22aa"` when targeting the 2.2 standard required by EN 301 549:2021.
- `aria-hidden="true"` on a focusable element hides it from the accessibility tree but does not remove it from the Tab order — the user lands on something that announces nothing. Always pair `aria-hidden` with `tabindex="-1"` or remove the element from the DOM entirely.
- VoiceOver on iOS processes `aria-live="polite"` differently from NVDA — test both; a single AT passing is not evidence of universal compliance.
- The EAA exemption for "disproportionate burden" requires documented evidence that the cost of remediation is unreasonably high relative to the organization's resources — it is not a blanket opt-out for complex features.
- axe-core Playwright integration runs in the browser context and cannot test server-rendered inaccessible markup that is replaced before hydration; audit the pre-hydration HTML separately with a static axe-core run via CLI.

## Verification

```bash
# 1. Run axe-core scan against staging
npx playwright test tests/a11y/ --reporter=html
# Review report at playwright-report/index.html

# 2. Query overdue SLA defects
wrangler d1 execute DB --command \
  "SELECT issue_number, wcag_criterion, wcag_level, sla_deadline FROM a11y_defects \
   WHERE status IN ('open','in_progress') AND sla_deadline < (strftime('%s','now')*1000) \
   ORDER BY sla_deadline ASC"

# 3. Validate ARIA on a specific page with CLI axe
npx axe https://staging.example.com/checkout --tags wcag2a,wcag2aa,wcag21aa --reporter json \
  | jq '[.[] | select(.violations | length > 0)]'

# 4. Check all issues labeled 'accessibility' with no 'verified' label in last 60 days
gh issue list --label accessibility --state open --limit 100
```

## Related

- `content-moderation-appeals-workflow.md` — appeals routing shares triage patterns
- `customer-reported-bug-intake.md` — general bug intake template
- `dark-patterns-deceptive-design-regulation.md` — UI compliance obligations
- `dsa-risk-assessment.md` — DSA systemic risk assessments include accessibility
- `support-to-engineering-handoff.md` — support → engineering escalation path

## Sources

- WCAG 2.1 and 2.2 — `www.w3.org/TR/WCAG21/`, `www.w3.org/TR/WCAG22/`
- EU Web Accessibility Directive 2016/2102
- European Accessibility Act (EAA) — Directive 2019/882, in force June 2025
- EN 301 549 v3.2.1 — Accessibility requirements for ICT products and services
- *Robles v. Domino's Pizza LLC*, 913 F.3d 898 (9th Cir. 2019)
- axe-core Playwright — `github.com/dequelabs/axe-core-npm`
- WebAIM Screen Reader Survey 10 (2024) — `webaim.org/projects/screenreadersurvey10`
