# business-continuity-design

**Issue:** An organization has no plan to operate during or after a catastrophic failure
**Date:** 2026-08-11
**Status:** documented

## Symptom / Context
A data center fire causes the engineering team to improvise recovery for days, with no documented procedures or communication plan.

## Pattern / Solution
Document a Business Continuity Plan covering communication trees, manual fallback procedures, customer communication templates, and vendor escalation contacts. Test with tabletop exercises. Assign roles before an incident.

## Gotchas
BCPs go stale as the system evolves. Treat the BCP as a living document with quarterly reviews. The plan must be accessible when primary systems are down so store it out-of-band.

## Related
disaster-recovery-architecture, observability-architecture, multi-region-architecture
