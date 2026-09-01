# Customer Success Telemetry Source Authority

Adoption telemetry answers the question "is the customer actually using what they bought?", and that answer drives renewal forecasts, health scores, and escalation decisions. When two dashboards disagree — one showing declining logins, another showing steady feature usage — teams resolve the conflict by seniority or convenience rather than by designation. This article establishes how an organization designates one authoritative adoption-telemetry source, and how every secondary view reconciles to it.

## Scope

Covers designation, documentation, and reconciliation of product usage and adoption telemetry used in customer-success decisions: health scores, renewal risk calls, adoption baselines, and executive reporting. Applies to system-of-record designation and the discrepancy-handling workflow when secondaries diverge. Does not cover instrumentation design (what events to emit), which belongs to product analytics engineering, nor does it cover personal-data access approval, which follows privacy governance. Where a contractual commitment defines a specific usage metric, the contract definition prevails for billing purposes and the discrepancy between contract metric and internal metric must be documented, not silently merged.

## Workflow or implementation guidance

1. **Designate the system of record by written decision, not accumulation.** A short designation memo names the authoritative store, the metric definitions it owns (activation, active user, feature-adopted, depth-of-use), the definition version, and the effective date. Authority is granted per metric family; the event store may be authoritative for feature usage while the entitlement system is authoritative for licensed counts, and each boundary is written down.
2. **Version every metric definition.** "Active user" changes over time — daily, weekly, and rolling-window variants must each carry an identifier so a trend spanning a definition change is annotated or excluded, never silently spliced.
3. **Publish a reconciliation cadence.** Each secondary dashboard, CRM field, and report declares its upstream source and joins a scheduled reconciliation: row counts, key figures, and per-account spot checks. The cadence is risk-proportional — weekly for figures entering health scores, monthly for exploratory views.
4. **Classify divergence before correcting it.** A mismatch is first classified: freshness lag, filter or definition drift, population difference (different tenant scoping), or genuine data loss. Only data loss opens an incident; the others open correction tickets against the secondary.
5. **Correct in one direction.** Secondaries conform to the authoritative source. If the authoritative source is itself wrong (an ingestion failure), fix it there and let downstream refresh — patching a secondary to look right while the primary stays wrong guarantees the conflict returns.
6. **Stamp provenance on every exported figure.** Reports carry source identifier, definition version, extraction timestamp, and filter population, so a figure quoted in a renewal packet can be traced and reproduced.
7. **Review designation annually and on platform change.** Re-platforming analytics, merging tenants, or a new entitlement model are triggers to reconfirm or re-designate authority, with a transition window where both sources are labeled.

## Controls

- No customer-facing or forecast-facing figure may cite an undesignated source; if the only available number is unofficial, the artifact must label it provisional and non-authoritative.
- Reconciliation break thresholds are defined per metric; a break above threshold blocks publication of dependent reports until explained.
- Access to raw event data follows least privilege and purpose limitation; reconciliation uses aggregates wherever the question can be answered in aggregate.
- Definition changes require change-control approval and a changelog entry; a definition change that moves a health score must be flagged in the next health-score review.
- The designation memo is itself versioned; superseded versions are retained so historical decisions can be interpreted against the authority that existed at the time.

## Validation evidence

Evidence of a working regime includes: the current designation memo with version and effective date; the metric-definition catalog with version identifiers; reconciliation run outputs showing compared values, break classification, and resolution status over at least two consecutive cycles; a sample traced figure (from a renewal document back through extraction identifier to source query); and the changelog of definition changes with their health-score impact annotations. A one-time reconciliation proves nothing — the evidence must show the cadence repeating and breaks closing.

## Failure modes and correction

- **Dashboard pluralism** (multiple tools treated as co-equal): enforce the designation by removing the metric from non-authoritative surfaces or labeling them clearly as derived, and re-run the disputed decision against the authoritative figures.
- **Silent definition drift** (a secondary recomputes the metric locally): move the computation upstream or register the secondary's definition as a distinct, named metric; never let two different numbers share one label.
- **Stale-currency decisions** (acting on a lagging source in a fast-moving event): annotate freshness on every surface and define a maximum acceptable age per decision type before the figure may be used.
- **Primary-source corruption**: treat as a data-quality incident — freeze dependent publications, communicate the uncertainty window, and reconstruct from raw event storage before resuming.

## Limitations

An authoritative source is authoritative about what it measures, not about truth: instrumentation gaps, untracked channels, and off-platform usage remain invisible no matter how disciplined the designation. Telemetry authority also cannot adjudicate contractual usage disputes, where the contract's defined measurement controls. Finally, reconciliation detects divergence between sources, not shared systematic error affecting both.

## Canonical sources

- [NIST SP 800-61 Rev. 2, Computer Security Incident Handling Guide](https://csrc.nist.gov/publications/detail/sp/800-61/rev-2/final) — event classification, evidence handling, and escalation discipline for telemetry divergence handling.
- [ISO/IEC 8000-8 Data quality](https://www.iso.org/standard/78939.html) — fundamentals of data quality applicable to authoritative-source designation and reconciliation.

Local procedures should track the edition in force; confirm standard currency before citing the ISO entry.
