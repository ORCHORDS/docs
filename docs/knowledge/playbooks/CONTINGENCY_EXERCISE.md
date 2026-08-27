# Contingency Exercise Playbook

## Trigger

Use when testing a contingency, disaster-recovery, or service-recovery plan through a tabletop, technical test, functional exercise, or other controlled exercise.

## Inputs

- current contingency or recovery plan;
- critical systems, dependencies, and recovery priorities;
- exercise objectives and scenario;
- expected recovery targets when defined;
- participants, observers, and evidence capture method.

## Steps

1. **Set objectives.** Define what capability, procedure, dependency, or recovery target the exercise will test.
2. **Choose the exercise type.** Select a tabletop, component test, functional exercise, or other format appropriate to the objective and risk.
3. **Define scope and safety boundaries.** Identify systems, participants, simulated actions, excluded actions, and conditions that would stop the exercise.
4. **Prepare evidence capture.** Decide how notifications, timings, recovery steps, failures, and observations will be recorded.
5. **Run the scenario.** Exercise the plan as written rather than silently correcting gaps during execution.
6. **Validate recovery behavior.** Where applicable, test backup restoration, alternate processing, connectivity, dependencies, and return to normal operations.
7. **Record deficiencies.** Capture unclear instructions, missing dependencies, unmet targets, communication failures, and other plan weaknesses.
8. **Conduct an after-action review.** Separate observed facts from assumptions and identify corrective actions with owners and due dates.
9. **Update and retest.** Revise the plan where required and schedule a focused retest for material deficiencies.

## Completion criteria

The exercise is complete when objectives and results are recorded, deficiencies have assigned corrective actions, the plan has been updated where necessary, and any required retest is scheduled.

## Sources

- NIST SP 800-34 Rev. 1, Contingency Planning Guide for Federal Information Systems: https://csrc.nist.gov/pubs/sp/800/34/r1/upd1/final
- NIST SP 800-84, Guide to Test, Training, and Exercise Programs for IT Plans and Capabilities: https://csrc.nist.gov/pubs/sp/800/84/final

## Scope note

Exercise depth should reflect system criticality and risk. This playbook does not require destructive testing of production systems.
