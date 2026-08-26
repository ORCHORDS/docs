# Children's Privacy 2026 — COPPA 2.0, State Age-Appropriate Design, and Developer Duties

> When: 2026 brings layered children's privacy obligations. The FTC's COPPA
> rule (updated) is the federal floor; California's Age-Appropriate Design
> Code Act (AADC), Maryland's MODPA, and the proposed federal COPPA 2.0 /
> Kids Online Safety Act (KOSA) layer on top. Treat all as live.
> Who: Any operator of an online service "likely to be accessed by children"
> (broadly defined to include services not directed at children but used by
> them). The "directed at children" defence is narrow and shrinking.

## Regulatory Stack (2026)

### Federal — COPPA (FTC Rule, 16 CFR Part 312)
Applies to operators of websites/services directed to children under 13, OR
operators with actual knowledge they collect personal data from children
under 13. 2026 FTC updates tighten:
- **Independent educational technology** may now be covered (narrowing the
  school-consent exemption).
- **Notification requirements** strengthened.
- **Data retention limits** — keep data only as long as needed for the
  disclosed purpose.
- **Data deletion on request** by parent or school.

### Federal — COPPA 2.0 (proposed/passed in 2026 cycle)
Would raise the protected age to **17**, prohibit targeted advertising to
minors, require "data minimisation" for minors, and create a "duty of care"
for operators. Even if the final text is narrowed, build to this direction.

### Federal — KOSA (Kids Online Safety Act)
Duty-of-care standard for platforms "likely to be accessed by minors."
Requires default safe settings, harm-prevention design, and minor-friendly
reporting tools. State AG enforcement.

### California — Age-Appropriate Design Code Act (AADC)
Applies to businesses offering an online service "likely to be accessed by
children" (under 18). Requires:
- **Privacy by default** — highest privacy settings by default for minors.
- **Data Protection Impact Assessments** for services likely to be accessed
  by children.
- **Estimate of age** with reasonable effort.
- No use of geolocation, profiling, or nudge techniques that could harm
  minors.

### Maryland — MODPA (effective Oct 1, 2025; enforcement through 2026)
Prohibits processing minors' personal data for targeted advertising, sale,
or profiling. Stronger than California's AADC in some respects.

### Other states
Texas (SCOPE Act), Utah (Social Media Regulation Act), and others impose
parental consent and design duties. Track the strictest combination.

## Symptom

A social app with a substantial teen user base (15-17) ships without any
age-estimation, default-safe settings, or DPIA. The app uses precise
geolocation by default, shows targeted ads, and uses engagement-maximising
nudge patterns (auto-play, infinite scroll, push notifications tuned for
addiction). Team assumes COPPA doesn't apply ("users are 13+"). This is a
multi-law violation: California AADC (no DPIA, harmful defaults), Maryland
MODPA (processing minors' data for targeted ads), and if any under-13 users
exist, COPPA.

## Developer Obligations (Synthesised Strictest Floor)

1. **Age estimation** — implement a reasonable method to estimate user age.
   Self-declaration is a start but not enough under California AADC. Reasonable
   methods include: declared age at sign-up, behavioural signals (with
   consent), third-party age-assurance services for higher-risk services.
2. **Highest privacy by default for minors** — all settings default to the
   most protective option. This includes: location off, profiling off,
   targeted advertising off, friend lists private, DMs from non-connections
   blocked.
3. **No targeted advertising to minors** — across COPPA 2.0 (proposed),
  MODPA, and AADC, the trend is prohibition, not opt-in. Build to
  prohibition.
4. **No sale of minors' data** — MODPA prohibits outright. Others require
  verifiable parental consent, which is operationally hard enough to be a
  de facto prohibition.
5. **No profiling of minors** without compelling justification documented in
   a DPIA. "Personalisation" and "recommendation" are profiling.
6. **DPIA for any service likely accessed by minors** — required by
  California AADC. Must address: design features that could harm minors
  (addictive patterns, dark patterns, exposure to harmful content), data
  flows, and mitigations.
7. **Verifiable parental consent** for under-13 users (COPPA). Acceptable
   methods: signed consent form, credit card transaction, government ID
   check, trained representative call. Email-only consent is NOT verifiable.
8. **Right to delete** — parents and minors must be able to request deletion
   of data collected from a child.
9. **No geolocation for minors** without clear, documented necessity.
   Disable by default.
10. **Limit engagement-maximising features** for minors — auto-play off by
    default, screen-time summaries available, notifications can be silenced
    for sleep hours.

## Gotchas

- **"Likely to be accessed by children" is broad.** California AADC's
  definition includes services that children actually use, even if not
  marketed to them. A general-audience app with a meaningful under-18
  population is in scope. The "but we're not for kids" defence fails.
- **Self-reported age is unreliable and not a compliance shield.** Teens
  lie about their age. Regulators know this. If your service attracts minors
  and you do nothing beyond a DOB field, you have actual knowledge for
  COPPA purposes once a pattern is evident.
- **Email-only parental consent does not satisfy COPPA.** The FTC requires
  "verifiable" consent. Email plus a delayed confirmation email is acceptable
  ONLY in narrow internal-use cases, NOT for data sharing, sale, or
  disclosure to third parties.
- **COPPA 2.0 raises the age to 17.** If passed, every "under-13 only"
  defence collapses overnight. Build to 17 now.
- **MODPA prohibits targeted advertising to minors outright.** There is no
  opt-in workaround. Build a separate, non-targeted ad pipeline for users
  identified or estimated as minors.
- **DPIAs for children's services must address design harms**, not just data
  security. A DPIA that only covers encryption and access controls does not
  satisfy AADC. It must address addictive design, dark patterns, and
  exposure risks.
- **School-context data has special rules.** COPPA's school-authorised
  exception allows schools to consent on behalf of parents for educational
  technology, BUT the operator may NOT use the data for commercial purposes
  (ads, profiling). The 2026 FTC updates narrow this further.
- **Geolocation is presumptively harmful for minors.** If your app uses
  precise geolocation and is likely accessed by minors, you need a documented,
  compelling reason. "Map feature" is not compelling. "Safety check-in to
  parents" might be.
- **Dark patterns in consent flows for minors are separately actionable.**
  California, Maryland, and federal proposals specifically target manipulative
  consent design. A pre-checked box nudging minors toward data sharing is a
  violation independent of the underlying data practice.
- **Right to erasure must extend to derived data.** If a model was trained
  on a child's data and can produce outputs tied to that child, deletion
  obligations extend to the training contribution. "We can't untrain the
  model" is not a complete defence — document the effort and residual risk.
- **Age-assurance vendors shift the burden but not the liability.** Using a
  third-party age-assurance service is good practice, but the operator
  remains liable if the service fails. Due-diligence the vendor.
- **KOSA's duty of care creates a reasonableness standard.** Document design
  decisions, alternatives considered, and safety trade-offs. The
  documentation IS the defence.

## Implementation Checklist

- [ ] Estimate user age with a documented, reasonable method.
- [ ] Default all settings to most-protective for estimated minors.
- [ ] Disable targeted advertising, profiling, and data sale for minors.
- [ ] Disable precise geolocation for minors by default.
- [ ] Conduct a child-focused DPIA covering design harms, not just data
  security.
- [ ] Implement verifiable parental consent for under-13 users (NOT email
  only).
- [ ] Provide deletion pathway for parents and minors.
- [ ] Disable engagement-maximising features for minors by default.
- [ ] Audit third-party SDKs for data practices — you inherit their COPPA
  obligations.
- [ ] Document design decisions for KOSA duty-of-care defence.
- [ ] Track COPPA 2.0 / KOSA / state law changes quarterly — landscape is
  shifting through 2026.
