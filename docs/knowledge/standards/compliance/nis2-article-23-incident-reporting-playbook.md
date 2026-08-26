# nis2-article-23-incident-reporting-playbook

The operational playbook for meeting **Article 23 of the NIS2 Directive**:
the strict 24-hour / 72-hour / 1-month incident-reporting timeline that EU
"essential" and "important" entities must follow when a "significant
incident" occurs. This is the developer-and-ops counterpart to the broader
`nis2-directive.md` and `nis2-directive-implementation.md` articles — it
covers the *concrete workflow* an engineering team needs to actually hit
the legal clock.

Timeline (Article 23):
- **T+0**: the entity becomes "aware" of a significant incident.
- **T+24h**: submit an **early warning** to the national CSIRT. May be
  initially assumed to be unlawful/under attack; update later.
- **T+72h**: submit an **incident notification** with initial assessment
  of severity, impact, and (if known) indicators of compromise.
- **T+1 month**: submit a **final report** including root cause, damage,
  remediation, and measures to prevent recurrence.

Missing any of these deadlines is itself a NIS2 violation, with fines up
to €10M or 2% of global turnover for essential entities.

## Symptom

- A CVE drops in a library you ship; the security engineer pings Slack
  "is this reportable under NIS2?" and nobody knows.
- Your on-call receives a ransomware indicator at 02:00 and spends the
  first 3 hours *deciding whether* to involve the CSIRT — burning the
  24h budget before the report is even drafted.
- Legal asks "when did the clock start?" and engineering says "we noticed
  weird logs on Tuesday" but nobody can prove when it became "aware."
- You sent the 24h warning but missed the 72h update, and the regulator
  has asked why.
- Your incident tickets don't capture the fields the final report needs
  (IoCs, affected data categories, cross-border impact), so the 1-month
  report takes a week of archaeology.

## Root cause

The 24h clock starts at **awareness**, not at confirmation. NIS2
"awareness" is broadly interpreted: if a competent person in your org has
a serious indication that a significant incident *may* have occurred, the
clock is running — even if you haven't confirmed root cause, scope, or
whether it was malicious. Teams lose the clock because:

1. No pre-agreed definition of "significant incident" tuned to their
   business.
2. No standing "is this reportable?" decision tree the on-call can apply
   in 5 minutes.
3. No pre-filled CSIRT report template, so drafting takes hours.
4. The 24h, 72h, and 1-month reports are treated as one big doc instead
   of three staged submissions.
5. Incident tickets don't capture the regulatory fields from the start.

## Gotchas

- **"Aware" is earlier than you think.** An SOC analyst seeing an EDR
  alert, a customer reporting leaked data, or an upstream vendor's breach
  notice can all start the clock. Document the awareness timestamp —
   regulators will ask.
- **Voluntary early reporting is safer than waiting.** If in doubt, file
   the 24h early warning with "may be unlawful, under investigation."
   Filing then discovering it wasn't significant costs little; *not*
   filing then discovering it was significant costs the fine.
- **Vendor and supply-chain incidents start YOUR clock.** If your cloud
   provider, SaaS vendor, or open-source dependency discloses a breach
   affecting your service, Article 23 applies to you independently.
   "It was AWS's fault" is not a defence for missing your own 24h.
- **Cross-border = multi-CSIRT.** An incident affecting entities in
   multiple member states may require notification to each national
   CSIRT, not just your home one. The EU Cooperation Group has a single
   point of contact (SPOC) directory — keep it bookmarked.
- **Ransomware payment notifications are separate.** Many member states
   (e.g., France, Germany) require a *separate* notification if you pay
   a ransom, often to law enforcement in addition to the CSIRT. Don't
   conflate the two.
- **The 1-month final report is the one regulators actually read.** Teams
   under time pressure produce a thin 24h/72h report and a thin final
   report. Invest the time in the final — root cause, lessons, controls.
- **Non-EU entities can be caught.** If you offer services to EU
   essential/important entities and your incident affects them, their
   NIS2 reporting flows back to you as a third party. Expect contractual
   notice SLAs tighter than 24h (often 4-12h).

## Fix / practical setup

1. **Define "significant incident" for your org in advance.** A short
   internal doc listing triggers, e.g.:
   - confirmed unauthorised access to production systems
   - confirmed exfiltration of customer or employee PII
   - service outage above X hours for Y% of customers
   - exploitation of a known CVE in production with active IoCs
   - vendor breach notice affecting your data
   Sign off with legal and the DPO; review quarterly.

2. **Pre-build three report templates** — early-warning (24h),
   notification (72h), final (1 month). Each is a fill-in-the-blanks
   form stored in your incident-management tool (PagerDuty, Jira Service
   Mgmt, etc.). Required fields include:
   - awareness timestamp (UTC) and source
   - affected systems/services
   - known or suspected impact (data, users, geographic scope)
   - whether the incident is ongoing
   - whether cross-border entities are affected
   - IoCs (for 72h+)
   - root cause and remediation (1-month report)

3. **Wire the on-call decision tree into your IR runbook.** First page of
   every Severity-1/2 incident: "Could this be a significant incident
   under NIS2? If yes or unsure, page the Incident Commander + DPO
   immediately." The IC's first action is to log the awareness timestamp.

4. **Maintain a CSIRT contact book.** One row per member state you may
   need to notify: CSIRT email/portal, SPOC, encryption key fingerprint
   (many CSIRTs accept only encrypted reports), out-of-hours phone.
   Re-verify quarterly — CSIRT contacts change.

5. **Set up three timers in your incident tool** at T+0:
   - 24h: "File early warning" task assigned to Incident Commander.
   - 72h: "File incident notification" task.
   - 1 month: "File final report" task.
   Auto-escalate each to the CISO if not closed.

6. **Stage the reports deliberately.** Do not try to write the final
   report at T+24h. The 24h warning can be five lines. The 72h update
   adds initial assessment and IoCs. The 1-month report is the
   comprehensive one — but it must be on time, so schedule a draft by
   T+2 weeks.

7. **Capture regulatory fields in the incident ticket from the start.**
   Add custom fields for IoCs, data categories affected, cross-border
   entities, awareness timestamp. Backfilling at T+1 month is what makes
   teams miss the deadline.

8. **Tabletop exercise quarterly.** Pick a realistic scenario (vendor
   breach, ransomware, misconfigured S3 bucket). Run the clock from
   detection through to filed reports. Measure the actual elapsed time
   to a submittable 24h warning — if it's over 4 hours, fix the process.

## References

- NIS2 Directive (EU 2022/2555), Article 23 (reporting obligations).
- NIS2 Directive, Article 21 (risk-management measures that must include
  incident handling).
- ENISA, "NIS2 Implementation Guidance" and the national CSIRT directory.
- For broader context: `nis2-directive.md`,
  `nis2-directive-implementation.md`, `security-incident-response-plan.md`,
  `gdpr-breach-notification-72h.md` (GDPR has a parallel 72h clock with
  different triggers — do not conflate).
