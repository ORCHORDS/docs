# Team Topologies and Organizational Design

**Date:** 2026-08-17
**Author:** the platform team
**Status:** published

## Symptom

Every team depends on every other team for something.
Pull requests sit waiting for approvals across
organisational boundaries. The platform team is
simultaneously trying to build shared infrastructure,
consult on every service design, and run the CI
pipeline. No one knows who owns the authentication
service. Delivery slows as the company grows from 10
to 30 engineers, when intuition says it should speed
up.

## Context

Team Topologies (Skelton & Pais, 2019) provides a
vocabulary and model for structuring engineering
organisations to minimise cognitive load and maximise
flow. The model defines four team types and three
interaction modes. The insight is that organisational
structure determines software architecture (Conway's
Law), so structuring teams deliberately produces
better systems than restructuring teams reactively
after the architecture has been shaped.

## 1. The Four Team Types

```
+-------------------------+-----------------------------------+
| Team Type               | Primary responsibility            |
+-------------------------+-----------------------------------+
| Stream-aligned          | Delivering value to a user or     |
|                         | customer segment end-to-end.      |
|                         | Owns the full build-run cycle.    |
+-------------------------+-----------------------------------+
| Enabling                | Helping stream-aligned teams      |
|                         | acquire new capabilities. Does    |
|                         | not own production systems.       |
+-------------------------+-----------------------------------+
| Complicated Subsystem   | Owns a component requiring deep   |
|                         | specialist knowledge (ML model    |
|                         | serving, payments DSP, search).   |
+-------------------------+-----------------------------------+
| Platform                | Provides self-service internal    |
|                         | capabilities to stream-aligned    |
|                         | teams. Reduces cognitive load.    |
+-------------------------+-----------------------------------+
```

The majority of teams in a healthy organisation are
stream-aligned. Platform and enabling teams exist to
reduce the burden on stream-aligned teams, not to
gate them.

## 2. The Three Interaction Modes

```
+--------------------+---------------------------------------+
| Mode               | When to use                           |
+--------------------+---------------------------------------+
| Collaboration      | For a bounded period when two teams   |
|                    | need to solve a problem together.     |
|                    | High bandwidth, high cognitive load.  |
|                    | Should have a defined end date.       |
+--------------------+---------------------------------------+
| X-as-a-Service     | Ongoing: a team consumes a platform   |
|                    | or subsystem through a stable API.    |
|                    | Low bandwidth. The default mode       |
|                    | between platform and stream teams.   |
+--------------------+---------------------------------------+
| Facilitating       | An enabling team works with a stream  |
|                    | team to transfer knowledge or unblock |
|                    | a capability. Temporary by design.   |
+--------------------+---------------------------------------+
```

Collaboration mode is expensive. If two teams are in
permanent collaboration, they should probably merge
or one dependency direction should become a service
boundary.

## 3. Cognitive Load per Team

Cognitive load is the amount of mental effort required
to do the work. Every service, technology, and process
a team owns adds to it. When cognitive load exceeds
capacity, quality and delivery both suffer.

Rules of thumb:
- A stream-aligned team should own 5–8 services at
  most. Beyond that, incidents fall through the cracks.
- Do not assign a team a new domain until you have
  removed something of comparable load.
- Count languages, frameworks, and deployment targets
  separately from services; each adds load.

```
Cognitive load inventory (example):

Team: checkout-experience
Services:
  - checkout-api            (Node.js, Kubernetes)
  - cart-service            (Python, Kubernetes)
  - promo-engine            (Go, Kubernetes)
Technologies:
  - PostgreSQL, Redis, Kafka
Deployment targets:
  - 2 regions, blue-green deploy
Total load score:  HIGH (at capacity)

Action: move promo-engine to a new sub-team or to the
        complicated-subsystem team before adding more.
```

## 4. The Team API Concept

Each team should define and publish a Team API: a
structured description of how others interact with it.
This makes interaction modes explicit and reduces
ad-hoc requests.

```yaml
# team-api.yaml — example for the platform team
team: platform-engineering
mission: >
  Provide self-service infrastructure primitives
  that enable stream-aligned teams to ship safely
  without needing ops expertise.

services_provided:
  - ci-cd-pipeline     # X-as-a-service
  - secrets-management # X-as-a-service
  - container-registry # X-as-a-service
  - observability-stack # X-as-a-service

how_to_request_help:
  channel: "#platform-support"
  sla: 1 business day for questions
  escalation: platform-oncall@example.com

how_we_do_not_help:
  - Writing application code for stream teams
  - Attending all architecture reviews
  - Owning stream-team services in production

current_interaction_modes:
  checkout-team: x-as-a-service
  search-team:   collaboration (ends 2026-09-01)
  ml-team:       facilitating (model deploy tooling)
```

Store `team-api.yaml` in the team's primary repository
and link it from the internal developer portal.

## 5. Applying Team Topologies at Startup Scale

Patterns for the growth stages most engineering teams
experience:

```
5 engineers (seed)
  Everyone owns everything. No formal teams.
  Conway's Law does not apply yet. Ship fast.

10-15 engineers
  Form 2-3 stream-aligned teams by user domain.
  One person part-time on platform concerns.
  No formal platform team yet; use Slack conventions.

15-25 engineers
  Extract a dedicated platform team (3-4 engineers).
  Define X-as-a-service boundaries for CI/CD,
  observability, and secrets.
  Identify any complicated subsystems (payments,
  search) that need specialist ownership.

25-40 engineers
  Add enabling team role (or rotation into existing
  senior engineers) to run tech radar, standards, and
  onboarding.
  Formalise Team APIs.
  Audit cognitive load per team; split teams that are
  at capacity before delivery slows.
  Begin measuring DORA metrics per stream team.
```

Do not hire for a team topology you have not yet
validated. A platform team of one does not provide
X-as-a-service; it provides a bottleneck.

## Anti-patterns

- A platform team that must approve every production
  deployment is a gate team, not a platform team;
  it adds cognitive load rather than removing it.
- Too many dependencies between stream-aligned teams
  signal that the domain split is wrong; revisit the
  service boundary before adding more engineers.
- An enabling team that never exits; if a capability
  transfer is permanent, the enabling team has become
  a shadow operations team.
- Ownership by committee: when a service has no
  single named team, incidents are always someone
  else's problem.
- Re-orgs that move people without moving system
  ownership; the architecture will resist the re-org
  and create shadow ownership.

## Gotchas

- Team Topologies describes team types, not org chart
  boxes; an engineer can be on a stream-aligned team
  and participate in an enabling rotation.
- Interaction modes change over time; review them
  quarterly and update the Team API accordingly.
- Conway's Law works both ways: if you want a microservice
  architecture, you must first have loosely coupled
  teams.
- In early-stage startups, premature topology design
  adds bureaucracy before it adds value; delay formal
  topology until the team reaches ~15 engineers.

## Verification

1. Every team can name its type (stream-aligned,
   enabling, complicated subsystem, or platform) and
   its primary interaction mode with each adjacent team.
2. Each team's `team-api.yaml` exists and was updated
   within the last 90 days.
3. Cognitive load inventory exists for each team and
   no team owns more than 8 services.
4. The platform team can demonstrate at least three
   self-service capabilities that stream teams can use
   without filing a ticket or waiting for approval.

## Related

- `documentation/categories/lessons/platform-engineering-internal-developer-platform.md`
- `documentation/categories/lessons/documentation-decays-without-ownership.md`
- `documentation/categories/lessons/engineering-manager-1on1-skip-level-meetings.md`
- `documentation/categories/lessons/focus-time-over-velocity.md`

## Source URLs (verified 2026-08-17)

- https://teamtopologies.com/key-concepts
- https://martinfowler.com/bliki/ConwaysLaw.html
- https://itrevolution.com/articles/team-topologies/
- https://platformengineering.org/blog/what-is-platform-engineering
