# ticket-aging-dashboards

**Issue:** Raw bug counts are a poor health signal. A backlog of 400 open bugs says nothing about whether the team is keeping up: 390 of them could be a week old while 10 critical ones rot silently for months, or the average age could be climbing 5 days per sprint while the headline count stays flat. Without age-aware measurement, triage effort gets allocated by recency and loudness rather than by how long items have actually waited, and the first evidence of an intake imbalance appears anecdotally — usually when a customer asks why a report filed in April is still untouched in August. A ticket aging dashboard turns age into a first-class, continuously visible metric, so backlog decay is caught while it is still a trend rather than an archaeology project. This article covers what to measure, how to bucket and visualize it, and how to keep the dashboard honest. It complements issue-staleness-automation (which retires dead items) and bug-triage-rotation-duty (which processes the queue): the dashboard is the measurement layer that tells both where to look.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Metrics worth putting on the dashboard

1. **Average and median age of open bugs.** GitLab replaced its cumulative bug-backlog chart with an average-bug-age chart precisely because total count masked drift; the average responds within days to a triage slowdown while the count can stay flat for weeks. Report the median too — a handful of ancient outliers drags the mean and the median reveals whether the problem is fleet-wide or concentrated.
2. **Age distribution in buckets, not a single number.** Buckets such as 0-7 days, 8-30, 31-90, 90-plus show the shape: a healthy queue is front-loaded, and growth in the 31-90 bucket is the early-warning signal that arrives before anything lands in 90-plus. Atlassian community practice for Jira dashboards is exactly this severity-by-age-bucket grid.
3. **Age sliced by severity or priority.** A 60-day-old cosmetic bug is a different problem from a 60-day-old data-loss bug. Cross-tabulating severity against age buckets makes the dashboard actionable, because the cells that must never be populated — high severity, high age — light up visibly.
4. **Time-in-state, not just time-since-creation.** A bug that sat untriaged for 40 days but has been actively worked for the last week is healthy; one that entered "in progress" three weeks ago with no commits is stuck. Aging charts in tools like Rally visualize item age against the flow to expose exactly this distinction between waiting and working.
5. **Count of items breaching an age SLA.** Define per-class thresholds (for example, critical acknowledged within 24 hours, fix-or-explicit-defer within 30 days) and chart the breach count. One glanceable red number per class is what turns the dashboard from descriptive to operational.

## Designing the visualization

1. **Lead with a stacked bar or heatmap of severity by age bucket.** This is the core view: rows for severity, columns for age buckets, cell values the count of open bugs. It answers "where is the rot" in a single look and scales from 50 to 5,000 open issues without becoming noise.
2. **Add a trend line of median age over time.** The bucket grid is a snapshot; the trend line shows velocity of decay. A flat median with a slowly growing 90-plus bucket tells a different story than a rising median across all buckets, and only the time series can show it.
3. **Make every cell drill down to the actual issues.** A dashboard that cannot answer "okay, which ten bugs are these" forces someone to re-derive the query by hand and the dashboard stops being consulted. Link each bucket to a live, sorted issue list.
4. **Mark intervention events on the trend line.** Annotations for "staleness bot enabled", "triage rotation started", or "two engineers on leave" turn the dashboard into a record of what worked, which is what makes it useful in retrospectives rather than only in the moment.
5. **Keep it on a wall or an auto-rotating display.** The dashboard only changes behavior if it is seen without being sought. Embedding it where the team already looks — the standup screen, the tracker's default landing tab — is half the value.

## Keeping the metric honest

1. **Expect the metric to be gamed, and design against it.** QA practitioners consistently warn that any single bug metric gets played: closing-and-reopening to reset age, mass-downgrading severity to empty the scary cell, or relabeling bugs as feature requests. Countermeasures: audit trails on severity changes, counting reopened items from their original creation date, and reviewing the dashboard jointly rather than handing it to one owner as a target.
2. **Pair count-based views with aging views.** Raw backlog count rewards closing easy old junk while ignoring fresh criticals; age-only views reward panic-closing anything that hits day 31. Shown together, the two views keep both failure modes visible.
3. **Do not set the dashboard itself as a performance target.** The purpose is to direct attention, not to grade the team. Once median age becomes an OKR, the number starts improving for reasons unrelated to actual responsiveness — the classic Goodhart failure, and the reason to add dimensions and context rather than optimize one figure.
4. **Distinguish stale-but-forgotten from deliberately deferred.** An old bug with a documented wontfix or deferred decision should not appear in the same red bucket as one simply abandoned. Explicit deferral labels keep the dashboard signaling neglect, not choices.
