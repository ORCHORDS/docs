# TMS Comparison: Tolgee vs Weblate vs Transifex (2026)

## Symptom

You need a Translation Management System and the choice feels arbitrary.
Each vendor's marketing claims to be "developer-first" and "AI-powered."
Picking wrong means either overspending on Transifex when you're a 3-person
team, or fighting Weblate's self-hosted ops when you wanted zero infrastructure.

This file gives a decision framework based on team size, hosting preference,
and whether you need AI translation baked in.

## At a glance (2026)

| Feature            | Tolgee           | Weblate           | Transifex         |
|--------------------|------------------|-------------------|-------------------|
| Hosting            | Cloud + self-host| Self-host + cloud | Cloud only        |
| License            | Apache 2.0       | GPL-3             | Proprietary       |
| AI translation     | Built-in (inline)| Plugin/addon      | Built-in (TaaS)   |
| In-context editing | Yes (SDK overlay)| Limited           | Via screenshots   |
| Pricing model      | Generous free tier| Free self-host   | Per-seat + words  |
| Best for           | Small/mid dev teams| OSS / on-prem   | Enterprise        |

## Decision guide

### Choose Tolgee if
- You want translators to click text directly in your running app
  (in-context editing is the killer feature).
- Team is small (1-20 devs) and you want AI MT without a separate contract.
- You're OK with a JS/React-centric SDK story.

### Choose Weblate if
- You must self-host (compliance, air-gapped, EU data residency).
- Project is open source -- Weblate gives free hosting to OSS projects.
- You already run Django/Python infrastructure.

### Choose Transifex if
- Enterprise with >50 translators, dedicated L10n team, SLA requirements.
- You need vendor workflows (multiple LSPs, review SLAs, audit trails).
- Budget is not the primary constraint.

## Gotchas

- **"Free tier" traps.** Tolgee cloud free tier limits keys/strings; once
  you cross ~1000 strings you pay. Weblate self-host is free but your
  server time is not -- factor in PostgreSQL + backups + upgrades.
- **In-context editing breaks on dynamically rendered text.** Tolgee's
  overlay hooks into the rendered DOM. SSR (Next.js, Nuxt) and
  canvas-rendered UIs (WebGL, some chart libs) will not be clickable.
  Plan for a hybrid: in-context for marketing, key-based for app strings.
- **Weblate's GPL-3 infects modifications.** If you fork Weblate itself to
  add a feature, you must publish under GPL-3. For most teams this is fine
  (you only use it, not modify it), but legal teams flag it.
- **Transifex pricing scales with seats AND translation volume.** A
  marketing-heavy app can blow the budget on words alone. Get a written
  quote for projected volume before committing.
- **AI features are not equal.** Tolgee's MT is integrated into the editor
  with one-click accept. Weblate AI is an addon that may require a separate
  API key (DeepL/Google/AWS) and configuration. Transifex AI (Livedocs +
  TaaS) is polished but adds per-word cost.
- **Git integration depth differs.** Weblate has the tightest Git
  round-trip (push PRs back to GitHub/GitLab natively). Tolgee does Git
  sync but PR review is manual. Transifex uses a CLI (`tx`) you call from CI.
- **Format coverage.** All three handle JSON/YAML/PO/XLIFF/gettext. But
  exotic formats (Flutter ARB, iOS stringsdict, ICU MessageFormat v2)
  have varying fidelity. Test your actual format before signing up.
- **Lock-in.** Exporting from Transifex is possible but the workflow
  metadata (review states, comments) is proprietary. Tolgee and Weblate
  export to open formats including their own JSON, which is portable.
- **SSO/SAML may cost extra.** Tolgee includes SSO on cloud paid.
  Weblate SSO is configurable self-host. Transifex gates SSO behind the
  Enterprise tier (~$$$).
- **Uptime for self-hosted = your uptime.** If translators can't reach
  Weblate because your Docker container crashed at 2am, that's on you.

## Quick checklist

1. List your formats (JSON/PO/ARB/stringsdict).
2. Decide: cloud vs self-host (compliance-driven).
3. Count seats + projected words/month for the next 12 months.
4. Trial top 2 with your real repo -- do not trust the demo data.
5. Check export: can you leave with all data in 1 hour if needed?
