# Cloudflare Waiting Room — Traffic Management, Queuing Methods, and Event Scheduling

**Date:** 2026-08-16
**Author:** the platform team
**Status:** published

## Symptom

Your e-commerce site launches a limited-edition product drop at noon.
Within 30 seconds, 50,000 users hit the product page simultaneously.
The origin server buckles under load — checkout times out, inventory
oversells, and the database connection pool is exhausted. Users
refresh aggressively, amplifying the thundering herd. Your CDN caches
static assets but the dynamic checkout flow hits origin directly.
You need to control the flow of users to origin without scaling
infrastructure for a 10-minute traffic spike.

## Context

Cloudflare Waiting Room sits in front of an origin application and
queues visitors when traffic approaches admin-defined thresholds,
preventing origin overload during surges (flash sales, ticket drops,
product launches). It runs on Cloudflare Workers across the global
network. Under normal load, visitors pass straight through. When
thresholds are approached, new visitors enter a virtual queue with
a waiting room page showing position and estimated wait time. Queued
visitors receive a cookie recording entry time and position. The page
auto-refreshes every ~20 seconds. Users who leave and return within
the session duration re-enter without re-queuing. Available on
Business ($200/month, one room, limited features) and Enterprise
(advanced features via add-on).

## Core configuration

```
Waiting Room settings:

  Total Active Users:    Max concurrent users on the origin
  New Users Per Minute:  Rate at which queued users are admitted
  Session Duration:      How long an admitted user's pass lasts
                         before re-queuing (tuning critical)

  Flow:
    1. User arrives → Cloudflare checks thresholds
    2. Under threshold → pass through, start session timer
    3. At/over threshold → enter queue, show waiting page
    4. Slot opens → admit next user from queue
    5. Session expires → user must re-queue if returning
```

## Queueing methods

```
Method        Behavior                        Use case
──────────────────────────────────────────────────────────────
FIFO          Orders by entry timestamp        Default, predictable
              cookie; rewards early arrival    standard queuing

Random        Randomly admits from the pool    Limited-drop sales,
              when capacity opens; lottery-    lottery-style fairness
              style access

Passthrough   All traffic passes through,      Instrument/observe
              no queuing; analytics still      traffic before an event
              collected                        without gating

Reject        Blocks all traffic with a        Maintenance windows,
              static page                      closed endpoints

Note: switching between FIFO and Random mid-event confuses
wait-time estimates and violates user fairness expectations.
```

## Event-based scheduling

```
Scheduled Events override the base waiting room settings
for a defined time window:

  Overridable per event:
    → Total Active Users
    → New Users Per Minute
    → Session Duration
    → Session Renewal
    → Queueing Method

  Pre-queueing:
    → Configurable window before event start
    → Arriving users held in queue before event begins
    → Optional shuffle at event start for random admission
    → Fairer than pure FIFO for hyped launches
    → Users arrive early, get shuffled, admitted randomly at T=0

  Example flow for a ticket sale at 10:00 AM:
    09:30 — Pre-queue opens, users start arriving
    10:00 — Event starts, queued users shuffled and admitted
    10:30 — Event ends, base waiting room settings resume
```

## Bypass rules

```
Enterprise Advanced feature:

  Expression-based rules that exempt matching traffic
  from the waiting room entirely.

  Bypass criteria:
    → IP address / range (admin access)
    → URI path (static assets, health checks)
    → Query string parameters
    → Country
    → File extension (.css, .js, .png)

  Use cases:
    → Admin/QA access during events
    → Static assets that don't need protection
    → Health check endpoints for monitoring
    → API endpoints with their own rate limiting
```

## Analytics and metrics

```
Available in all modes (including passthrough):

  Real-time metrics:
    → Active users on origin
    → New users per minute
    → Current queue size
    → Queue wait time

  Historical metrics:
    → Peak concurrent users
    → Total users queued
    → Average wait time
    → Time-on-origin per session

  Passthrough mode:
    → Use before an event to baseline traffic
    → Measure actual load without gating
    → Tune thresholds based on real data
```

## Pricing

```
Tier          Rooms  Custom page  Events  Bypass rules
──────────────────────────────────────────────────────────────
Free/Pro      —      —            —       —
Business      1      Basic        No      No
Enterprise    Many   Advanced     Yes     Yes
(Advanced)           (full HTML)

Enterprise Advanced add-on required for:
  → Custom HTML/CSS waiting room templates
  → Scheduled Events with pre-queueing
  → Bypass rules
  → Granular path protection
  → Multiple waiting rooms
```

## Anti-patterns

- **Setting thresholds from guesswork** — load-test the origin
  to determine actual capacity before configuring Total Active
  Users. Under-provisioning queues unnecessarily; over-provisioning
  defeats the purpose.
- **Switching queueing method mid-event** — changing FIFO to
  Random (or back) during an active event confuses wait-time
  displays and violates the fairness expectations users built up.
- **Session duration too short** — forces repeat queuing for
  slow checkout flows. Users who take 15 minutes to complete
  purchase get re-queued if session expires at 10 minutes.
- **Not bypassing static assets** — queuing CSS, JS, and image
  requests wastes queue capacity on non-critical traffic. Use
  bypass rules for static asset paths.
- **Assuming Waiting Room stops bots** — it queues by session
  cookie, not identity. Scalpers use multiple sessions. Pair
  with Cloudflare Bot Management for bot-heavy launches.

## Gotchas

- **Session duration vs checkout time** — session duration must
  exceed your longest expected user journey (browsing + checkout
  + payment). Measure actual user session lengths before setting.
- **Cookie-based session tracking** — users in private/incognito
  mode or clearing cookies lose their queue position and session.
  This is by design but can frustrate legitimate users.
- **Pre-queue shuffle timing** — shuffle happens at event start
  time, not when pre-queue opens. Users arriving 30 minutes early
  and 1 minute early have equal chances with random shuffle.
- **Advanced features require Enterprise** — custom HTML templates,
  scheduled events, and bypass rules all require Enterprise with
  the Advanced add-on. Business tier gets basic functionality only.

## Verification

- Waiting Room configured with load-tested origin capacity thresholds.
- Queueing method selected before event start and not changed during.
- Session duration exceeds longest expected user journey.
- Bypass rules configured for static assets and health checks.
- Passthrough mode used to baseline traffic before first event.
- Bot Management paired with Waiting Room for high-value launches.

## Related

- `documentation/docs/policies/cloudflare/rate-limiting-workers-rules.md`
- `documentation/docs/policies/cloudflare/workers-ai-inference-gateway.md`
- `documentation/docs/policies/performance/edge-computing-serverless-latency.md`

## Source URLs (verified 2026-08-16)

- Cloudflare Waiting Room Documentation — https://developers.cloudflare.com/waiting-room/about/
- Queueing Methods Reference — https://developers.cloudflare.com/waiting-room/reference/queueing-methods/
- Scheduled Events Configuration — https://developers.cloudflare.com/waiting-room/additional-options/create-events/
- Bypass Rules for Waiting Room — https://developers.cloudflare.com/waiting-room/additional-options/waiting-room-rules/bypass-rules/
