# weekly-summary-email

**Issue:** Building automated weekly summary emails with user-specific activity data
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
Weekly digests (GitHub contribution summaries, Slack activity recaps, analytics reports) drive retention by showing value.

## Pattern / Solution
Architecture:
1. Scheduled job runs Sunday night (or Monday morning per user's timezone).
2. Queries each user's activity data for the past 7 days.
3. Renders personalized template with stats, highlights, recommendations.
4. Sends in batches via ESP.

Template structure:
- Hero stat: most impressive number ("You completed 12 tasks this week").
- Comparison: vs. prior week ("Up 20% from last week").
- Highlights: top 3 activities.
- Nudge: suggested next action.

```js
const weeklyData = await computeWeeklySummary(userId, startOfWeek, endOfWeek);
await emailQueue.add('send', { to: user.email, template: 'weekly-summary', data: weeklyData });
```

## Gotchas
- Users with no activity in the period should receive a skipped send or a re-engagement email instead.
- Timezone-aware scheduling is essential; 9am Monday in their timezone, not UTC.
- Compute data asynchronously before send time; real-time computation at send time doesn't scale.

## Related
- email-scheduling-patterns, email-personalization-patterns, email-dynamic-content, email-batch-sending
