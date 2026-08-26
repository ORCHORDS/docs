# Alert Fatigue Management

## Symptom

On-call engineers stop responding to pages. Alerts pile up unread in Slack,
phones are set to Do Not Disturb "just for tonight," and when a real P0
outage fires at 3 AM, the on-call engineer sleeps through it because they have
been desensitized by 200 noisy pages that week. Meanwhile, nobody notices the
MTTA (mean time to acknowledge) creeping from 4 minutes to 40 minutes over a
quarter, because each individual alert "seemed fine to ignore."

The deeper symptom is cultural: engineers start treating alerts as ambient
background noise rather than actionable signals. A senior engineer says "oh,
the 502 alert fires every deploy, just ignore it for 10 minutes." That
institutionalized ignoring is the failure mode — because the 502 alert will
also fire during a real backend outage, and now nobody is watching.

Alert fatigue is a leading indicator. If left untreated, it guarantees a
missed P0 within 6-12 months, followed by a blameless postmortem whose root
cause reads "the on-call engineer did not acknowledge the page for 47
minutes."

## Common Root Causes

- **Alerting on symptoms, not causes.** A CPU-high alert fires because of a
  noisy-neighbor process, not because user traffic is degraded. The engineer
  investigates, finds nothing wrong, and mentally files the alert as noise.
  Next time, same alert = same assumption.
- **Alert thresholds calibrated on dev-environment load.** Thresholds set to
  "2x normal traffic" that fire during every legitimate traffic spike (Black
  Friday, product launch, news event). These are not incidents — they are
  successes.
- **Duplicate alerts across layers.** A database goes down and generates a
  page from: the DB health check, the application error-rate alert, the
  synthetic monitor, the dashboard "service unhealthy" widget, and the
  upstream consumer's timeout alert. Five pages for one incident.
- **Low-severity alerts routed to the same pager as P0.** A disk-80%-full
  warning (fix within a week) pages the same on-call engineer as a production
  outage. The brain cannot maintain a different urgency level per page when
  they all vibrate the phone the same way.
- **Alerts with no runbook.** "Error rate elevated on /api/checkout." Then
  what? The engineer has to reverse-engineer what to do, often concluding
  "it resolved itself" and learning to dismiss it.
- **Stale alerts from decommissioned systems.** Nobody removed the alert for
  the old payment service that was replaced 8 months ago. It fires into the
  void, or worse, into the general on-call channel.

## Gotchas

- **"We'll just tune thresholds later" never happens later.** Threshold
  tuning is maintenance debt that compounds. Every noisy alert that ships
  makes the next noisy alert easier to accept. Set a policy: any alert that
  fires >3 times without action item creation within 30 days must be tuned or
  deleted.
- **Auto-grouping is not auto-fixing.** Tools like PagerDuty's "Alert
  Grouping" or incident.io's deduplication reduce page volume, but they do
  not fix the underlying root cause (duplicate alerting across layers).
  Grouping can also accidentally swallow a real incident into an existing
  incident's grouping window — verify grouping windows are tight (5-10 min,
  not 60 min).
- **Slack alerts ≠ pages.** If a human needs to act, it pages (wakes them
  up). If it's informational, it posts to Slack (read when convenient).
  Mixing these channels — paging for informational items, or Slack-only for
  actionable items — destroys the signal-to-noise ratio of both.
- **"Test alerts" desensitize the pager.** Running a fire drill by paging the
  real on-call rotation trains everyone that "this page might be a drill."
  Use a separate test-escalation policy with a clear "DRILL" prefix so real
  pages maintain urgency.
- **On-call engineers won't self-report fatigue.** Admitting "I ignored 12
  alerts last shift" feels like admitting negligence. Track fatigue
  objectively via metrics (alert-to-action ratio, MTTA trend, auto-ack
  rate), not via self-report.
- **"Just add more alerts to be safe" is the failure mode.** A nervous team
  adds alerts defensively ("we don't want to miss anything"), inflating
  noise. Fewer, higher-quality alerts catch more real incidents than many
  low-quality ones.

## Remediation Workflow

1. **Audit alert-to-incident ratio.** Pull 90 days of pages and 90 days of
   incidents. Ideal ratio: 1 page per 1 incident (or 1 page per incident +
   0.2 false positives). If you page 200 times and have 20 incidents, you
   have an 80% noise problem.
2. **Categorize every alert.** For each alerting rule, assign one of:
   **keep** (catches real incidents), **tune** (right signal, wrong
   threshold), **route-to-Slack** (informational, not actionable), or
   **delete** (no longer relevant). Do this in a single batch sprint, not
   incrementally.
3. **Implement multi-level urgency.** PagerDuty/OpsGenie support
   "high-urgency" (pages, wakes you up) vs "low-urgency" (notifies, doesn't
   wake). Route only P0/P1 to high-urgency. Everything else is low-urgency
   or Slack-only.
4. **Enforce the "alert must link to a runbook" rule.** Any alert without a
   linked runbook page is auto-disabled after 14 days. If you cannot document
   what to do when it fires, it is not actionable.
5. **Review monthly.** Alert fatigue returns. Set a monthly review of the
   top 10 noisiest alerts and tune or delete them. Publish the "alerts
   killed this month" count to reinforce that noise reduction is valued.

## Prevention

- **Alert on SLO burn rate, not raw metrics.** Instead of "error rate > 1%"
  (which fires during normal variance), alert on "SLO error budget burning
  at >2x normal rate over 1 hour." This correlates to actual user impact.
- **Adopt a "page for action, dash for awareness" rule.** If the recipient
  must do something now: page. If they just need to know: dashboard. No
  middle ground.
- **Set a budget on page volume.** A team of 5 on a weekly rotation should
  not receive more than N pages per on-call shift (e.g., 5). If the budget
  is exceeded, trigger an automatic alert-quality review. Make noise a
  measured, owned metric — not an untracked externality.
- **Quarterly fire drills with real alerting.** Verify that the alerts you
  expect to fire during a real incident actually fire, and that the ones you
  expect to stay silent actually stay silent. Stale alerting logic rots.
