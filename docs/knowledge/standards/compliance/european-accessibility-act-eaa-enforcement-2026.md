# european-accessibility-act-eaa-enforcement-2026

**Issue:** The European Accessibility Act (Directive (EU) 2019/882) applies to products and services placed on the EU market from 28 June 2025, and unlike GDPR it is enforced entirely through 27 different national regimes with their own authorities, penalty scales, and even criminal exposure in Ireland. For engineering teams, the shift in 2025-2026 is from aspiration to enforcement: the first EAA lawsuits were filed in France in November 2025, courts have since ordered major retailers like Carrefour and Auchan to make their e-commerce services accessible, and other member states are queuing up enforcement programs. A product that ships inaccessible checkout flows is now a direct litigation and market-withdrawal risk, not just a WCAG best-practice gap.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## Scope And Application Dates

1. **Covered services.** E-commerce (including marketplace and marketplace-style listings), banking and financial services for consumers, e-books, transport services, telecoms, and passenger transport services are the main digital scope; each must meet the accessibility requirements of Annex I, not merely "be accessible" in the abstract.
2. **Covered products.** General-purpose computers, operating systems, smartphones, self-service terminals (ATMs, ticketing, check-in machines), and e-readers with digital talking-book functionality carry product requirements plus user documentation requirements.
3. **Legacy services runway.** Services provided before 28 June 2025 that remain unchanged get until 28 June 2030 to conform; any substantial change to the service collapses that runway and brings it into scope immediately, so feature teams need a definition of "substantial change" from counsel.
4. **Micro-enterprise exemption is narrow.** Enterprises with fewer than 10 staff and under EUR 2 million turnover are exempt for services only — product requirements still apply, and the exemption evaporates the moment the company grows past either threshold.
5. **Pre-2022 contracts exception.** Services supplied under contracts signed before 28 June 2022 remain out of scope until contract renewal, which matters for long-tail B2B SaaS deals.

## National Enforcement Landscape

1. **No EU-level enforcer.** The Commission does not enforce the EAA; each member state designated a market-surveillance or consumer authority — Germany's BFSG regime (Market Surveillance of the Länder), Ireland's CCPC, France's DGCCRF, the Netherlands' ACM — and penalties range from administrative fines in the tens or hundreds of thousands of euros to market bans.
2. **Ireland's criminal exposure.** Ireland is the only member state attaching criminal penalties, with fines and imprisonment (up to 18 months for service-provider violations in the transposing act), which raises the stakes for companies routing EU operations through Dublin.
3. **France as the bellwether.** Disability organizations filed the first EAA lawsuits in November 2025 against major retailers, and 2026 court orders have required Carrefour and Auchan to make online commerce services fully accessible — demonstrating fast-moving consumer-standing litigation rather than slow regulator action.
4. **Divergent national implementations.** Some states added broader scope or extra duties in transposition (Germany's BFSG notably exceeds minimums), so a single "EU compliance" flag in config is wrong; track obligations per member state of operation.
5. **Enforcement ramp through 2026.** The Netherlands and other member states have signaled 2026 enforcement programs, and consumer associations across the EU have standing to demand corrective action, meaning demand letters will precede most formal proceedings.

## Conformity Engineering

1. **EN 301 549 as the compliance path.** Conformity with the harmonized standard EN 301 549 (which incorporates WCAG 2.1 AA plus additional software and hardware clauses) creates a presumption of conformity; map every EAA Annex I requirement to specific EN 301 549 clauses in your traceability matrix.
2. **E-commerce requirements go beyond WCAG.** Annex I requires accessible product information, identification and handling of accessibility problems in the purchase journey, and accessible payment flows — including two-factor authentication paths that screen-reader users can complete, a common failure point.
3. **Accessibility statement.** Services must publish an accessibility statement using the Commission's model, describing conformance level, known failures, and a feedback channel with a response commitment; generate it from the test system so it cannot drift from reality.
4. **Product conformance and CE-style logic.** For products, build a technical file with design specifications, test reports, and the EU declaration of conformity; self-service terminals need both software and physical ergonomics evidence.
5. **Third-party components.** Marketplace listings, embedded payment widgets, and chat vendors flow into your obligations; flow EAA requirements down contractually and run accessibility acceptance tests on vendored components at upgrade time.

## Compliance Evidence And Tooling

1. **CI-level automated checks.** Run axe-core or equivalent on every page state in CI to catch regressions in labels, contrast, and focus order; automated tooling catches only a minority of issues, so treat it as a floor.
2. **Periodic manual audits.** Screen-reader pass testing (NVDA, VoiceOver, TalkBack), keyboard-only walkthroughs of the full purchase funnel, and cognitive-load review of checkout flows at least annually and before major releases.
3. **ACR publication.** Produce an Accessibility Conformance Report (VPAT-based, EN 301 549 edition) for enterprise deals; European buyers increasingly request it as contract condition.
4. **Defect registry with SLAs.** Track accessibility bugs in the same tracker as security bugs with severity ratings and fix SLAs — a dated register of known issues and remediation progress is the first thing French courts asked for.
5. **Support-service accessibility.** Support channels (chat, phone queues, docs) must themselves be accessible and documented in the statement, including relay-service compatibility.

## Adjacent Regimes

1. **Web Accessibility Directive (2016/2102) is separate.** Public-sector bodies have had EN 301 549 duties since 2019 plus a monitoring regime; if you sell to public bodies you may be contractually bound to it even when the EAA does not apply.
2. **Overlap with the existing WCAG article.** This KB already covers WCAG 2.1 technical compliance; the EAA layer adds product scope, enforcement bodies, statements, and litigation risk that pure-standards work does not address.
3. **Global patchwork.** The EAA coexists with the US ADA (litigation-driven), Section 508 (federal procurement), and similar regimes in Canada (ACA) and Australia (DDA); architect one conformance target at EN 301 549/WCAG 2.1 AA and evidence it per jurisdiction rather than building region-specific accessibility.
