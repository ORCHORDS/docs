# Backup and Restore Validation Playbook

## Trigger

Use on the scheduled backup-testing cadence, after material backup-system changes, and before relying on backup data for a significant recovery.

## Inputs

- recovery objectives and prioritized services;
- backup inventory and retention policy;
- encryption/key and access requirements;
- restore procedure and dependencies;
- isolated or otherwise safe validation environment where appropriate.

## Steps

1. **Select the recovery target.** Choose representative systems or data based on business criticality and defined recovery objectives.
2. **Confirm backup availability.** Verify the expected backup exists, is accessible to authorized recovery personnel, and matches the intended recovery point.
3. **Protect the test.** Restore in a way that does not overwrite production data or expose sensitive information unnecessarily.
4. **Restore from the backup.** Follow the documented procedure, recording elapsed time, dependencies, errors, and manual interventions.
5. **Validate integrity.** Confirm restored data and systems are complete enough for the intended recovery purpose and check integrity before production use.
6. **Validate functionality.** Test the critical functions needed to resume service, not merely whether files can be extracted.
7. **Compare objectives.** Record actual recovery time and recovery point against the organization's targets.
8. **Correct gaps.** Update procedures, retention, access, capacity, automation, or training when the exercise exposes a weakness.

## Escalation

Escalate immediately when a required backup is missing, unreadable, unexpectedly incomplete, cannot be decrypted by authorized personnel, or cannot meet a critical recovery objective.

## Completion criteria

A validation cycle is complete when restore evidence is recorded, integrity and required functionality are confirmed, observed recovery performance is compared with objectives, and all material gaps have owners.

## Sources

- NIST — Cybersecurity Framework 2.0 Resource & Overview Guide, including Recover guidance: https://www.nist.gov/cyberframework
- CISA — StopRansomware Guide: https://www.cisa.gov/stopransomware/ransomware-guide

## Scope note

Backup requirements vary with business, legal, regulatory, and data-retention obligations. This playbook provides project-neutral recovery validation guidance.
