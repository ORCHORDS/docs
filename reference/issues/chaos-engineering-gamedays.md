# Chaos Engineering and Game Days

## Symptom

The team discovers, during a production P0 at 2 AM, that their failover
mechanism has been silently broken for 6 months. The secondary database was
marked "healthy" in the dashboard, but the replication lag had grown to 4
hours and nobody noticed — because nobody had ever actually triggered a
failover outside of the original setup. The system "worked" in theory, passed
every health check, and failed catastrophically the first time reality
tested it.

Or: the team has a beautifully documented incident response runbook that has
never been exercised. When a real incident fires, the runbook's step 3
("escalate to the DBA on-call") fails because the DBA rotation was
disbanded. The runbook was written, merged, and never revisited — a
load-bearing document with zero validation.

The symptom is overconfidence in untested resilience. Systems and processes
that have never been stressed accumulate hidden failure modes. You find them
either proactively (chaos engineering, game days) or reactively (during a
real incident, at the worst possible time).

## Common Root Causes

- **Resilience is assumed, not verified.** "We have multi-AZ redundancy" —
  but the cross-AZ failover has never been tested in production. The
  configuration was correct at deploy time; nothing verifies it stays
  correct as the system evolves.
- **Runbooks are write-once-never-tested.** A runbook written during onboarding
  is treated as permanent truth. Services get renamed, runbooks don't, and
  the first person to follow the runbook during an incident discovers step
  2 references a deleted dashboard.
- **On-call engineers are unprepared.** A new engineer joins the rotation
  having never handled a real incident. Their first incident is a P0 at 3 AM.
  They fumble the paging tool, the war room setup, the comms. This is a
  training failure, not an engineer failure.
- **"We can't test in prod" becomes "we don't test at all."** Legitimate
  concerns about disrupting production metastasize into a policy of never
  testing resilience anywhere. The blast-radius concern is real; the
  conclusion ("so let's never test") is wrong.
- **Failure modes are not catalogued.** Nobody has sat down and asked "what
  are the top 10 ways this system fails?" Without a failure catalog, there
  is no target list for chaos experiments. You test what you can think of
  in the moment, which is a subset of what will actually break.

## Gotchas

- **Chaos engineering without observability is just sabotage.** If you
  inject failure (kill a pod, add latency, drop traffic) into a system you
  cannot observe, you learn nothing. The experiment must have a hypothesis
  ("if we kill pod X, traffic reroutes within 2s with no user-visible
  errors") and the observability to verify the outcome. No observability =
  no experiment, just damage.
- **Game days without executive buy-in will be blocked.** Someone in
  leadership will say "you want to intentionally break production? No."
  Frame it correctly: game days are how we find the broken things before
  customers do. Run them in staging first, build confidence, then
  carefully scope production experiments. The default production scope
  should be "minimal blast radius, during business hours, with finger on
  the kill switch."
- **Unstructured game days become debugging sessions.** "Let's just break
  stuff and see what happens" produces noise, not signal. Every game day
  needs: a hypothesis, a defined blast radius, a success criterion, a
  rollback plan, and an observer who is not injecting failure (so they can
  document what actually happened).
- **Chaos Monkey-style random termination is the shallow end.** Randomly
  killing instances tests one failure mode (instance loss). The interesting
  failures are correlated: "what if the entire AZ goes down," "what if the
  dependency we assumed was reliable gets slow (not down, slow)," "what if
  the config service returns stale data." Design experiments for the failure
  modes that scare you, not the easy ones.
- **Post-game-day action items get deprioritized.** The game day reveals
  that failover takes 90 seconds (not the assumed 5). Everyone agrees this
  is bad. The action item goes into a backlog and dies there, because "it's
  not actively breaking anything." Game day findings without enforced
  remediation SLAs are theatre.
- **Simulated incidents don't capture real stress.** A game day at 2 PM on
  a Tuesday with coffee does not replicate the cognitive load of a real P0
  at 3 AM after a week of poor sleep. Game days build process muscle memory,
  but they under-prepare engineers for the human factors of real incidents.
  Supplement with on-call shadowing.
- **Testing only the technical system misses the human system.** A game day
  that tests "does the database failover work" but not "does the on-call
  engineer know who to page" is testing half the incident response. Include
  the human workflow: paging, war room setup, comms drafting, escalation.

## Game Day Workflow

1. **Define the scenario and hypothesis.** Write it down before the game
   day: "Scenario: primary DB becomes unresponsive. Hypothesis: read
   traffic fails over to replica within 30s; write traffic queues and
   recovers within 5 min of primary restoration. Blast radius: staging
   environment, no production traffic affected."
2. **Pre-brief stakeholders.** Notify anyone who might see dashboards turn
   red: "On Thursday 2-4 PM we are running a game day in staging. Expect
  red alerts; they are expected, do not escalate."
3. **Assign roles.** Injector (performs the failure injection), observer
   (documents timeline and outcomes), comms (handles any external
   questions), rollback owner (ready to restore if the experiment goes
   sideways).
4. **Run the experiment with a live timeline.** Record what happens at each
   timestamp: "T+0s: killed primary. T+8s: dashboard shows degraded. T+22s:
   failover triggered. T+35s: read traffic restored. Hypothesis: partially
   confirmed (failover within 30s confirmed; write queue behavior not as
   documented)."
5. **Capture action items with owners and deadlines.** Every deviation from
   the hypothesis generates an action item. Assign an owner and a deadline
   in the same tool used for incident postmortem action items, so they have
   the same tracking rigor.

## Prevention

- **Schedule game days regularly, not reactively.** Quarterly minimum for
  critical systems. Tie them to the on-call rotation so every engineer
  participates in at least one game day per cycle.
- **Maintain a failure mode catalog.** For each critical service, document
  the top 5-10 ways it can fail. This becomes the experiment backlog.
  Update it after every real incident (the incident revealed a failure mode;
  add it to the catalog and design a future game day around it).
- **Run game days in CI for automated chaos.** Tools like Gremlin, Chaos
  Mesh, or Litmus can run small chaos experiments continuously in staging
  as part of the deployment pipeline. Catch regressions in resilience
  automatically, not manually.
- **Onboard new on-call engineers via game days.** Before a new engineer
  takes a primary on-call shift, have them run (not just observe) a game
  day. This is the safest way to give them incident muscle memory before
  they encounter a real one.
- **Treat runbooks as code: test them.** A runbook is documentation that
  load-bears during incidents. Exercise it during game days; if a step
  fails, the runbook is broken (not the engineer following it). Version
  runbooks and mark the last-tested date.
