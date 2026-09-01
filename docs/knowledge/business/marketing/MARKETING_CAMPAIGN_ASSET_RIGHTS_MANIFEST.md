# Marketing Campaign Asset Rights Manifest

Every campaign asset is a bundle of permissions with a picture attached. The photograph carries a photographer's license and model releases; the music carries a synchronization license with territory and term limits; the talent carries usage rights priced by medium and duration; the typeface carries seat restrictions; the stock clip carries an editorial-only flag that a paid social ad violates. This article governs the rights manifest: the single record that states, for each campaign asset, who holds what right, for which use, in which territory, for how long, and what happens when the term ends. Campaigns fail audits not because rights were never acquired but because nobody could prove the scope of what was acquired.

## Scope

This control covers rights documentation for assets used in marketing campaigns: licensed and commissioned photography, video footage, stock media, music and sound recordings, voice performances and on-camera talent, fonts, illustration, generated and composited imagery, licensed third-party trademarks and logos, user-generated content reused with permission, and archival assets reused in new campaigns. It applies to paid media, owned channels, packaging-adjacent marketing, event materials, and internal creative tooling libraries.

It governs the manifest, the scope fields, the renewal and expiry machinery, and the takedown path when scope runs out. It does not negotiate licenses, set royalty rates, or adjudicate trademark disputes; it makes the acquired scope legible and enforceable.

## Workflow or implementation guidance

1. **Register every asset at intake with a rights entry.** No asset enters the creative library without a manifest record: asset identifier, source, acquisition date, contract reference, license type, and the scope fields. Screenshots, free downloads, and assets that arrive by email follow the same path; provenance ambiguity is itself a recorded state.
2. **Record scope in the five dimensions that actually break.** For each asset the manifest states: permitted media and channels, permitted modifications, territory, term with explicit end date or renewal terms, and attribution or on-screen credit obligations. Optional fields capture exclusivity, sub-licensing rights, and sensitivity restrictions such as talent usage in other contexts.
3. **Separate composition rights from component rights.** A finished video containing licensed music, talent performances, and stock b-roll inherits the narrowest scope of its components. The manifest computes the effective campaign scope as the intersection of component scopes, and renders that intersection to the campaign planner as the usable window.
4. **Bind campaigns to assets, and rights to campaigns.** Each campaign record lists the assets it uses; each manifest entry lists the campaigns using it. This cross-reference is what allows an expiring license to name every live placement it would strand.
5. **Enforce territory in trafficking.** Campaign scheduling checks asset territory against placement geo-targeting; a worldwide placement containing an asset licensed for one region is blocked at trafficking rather than discovered by the licensor.
6. **Run expiry machinery.** The manifest drives alerts ahead of term end: at a defined lead, renewal decisions are required, and absent renewal the asset moves to expired state, which removes it from new placements and generates a takedown list for live ones.
7. **Re-clear on re-use.** Archival assets pulled into a new campaign are re-checked against the new campaign's media, territory, and term; an old license rarely covers a new channel class, and re-use is the most common vector for scope violations.
8. **Handle user-generated and generated content explicitly.** UGC reuse carries a recorded permission from the creator with the scope granted; generated or composited imagery carries a record of the tool, prompt provenance where material, and a check against training-data indemnity terms where the vendor offers them.

## Controls

- Library write access requires a manifest entry; the asset management system rejects unregistered uploads into campaign-visible collections.
- Effective campaign scope is machine-computed from component intersection; planners see the computed window, not a remembered one.
- Trafficking integrates the expiry and territory checks as blocking conditions.
- Talent usage beyond the original engagement, including extended runs or new media classes, requires a documented extension before the extension runs.
- Contracts and licenses are stored attached to manifest entries, with a named owner accountable for renewal decisions.
- Periodic audits sample live placements against manifest scope, and every mismatch becomes a takedown or a renewal action with a deadline.

## Validation evidence

- Manifest extracts for sampled live assets showing license reference, scope fields, term, and attached contract documents.
- Campaign-to-asset cross-reference reports demonstrating that each live placement maps to assets in scope for its media, territory, and flight dates.
- Expiry alert and disposition logs: lead-time alerts sent, renewals executed, assets moved to expired, takedowns completed.
- Trafficking block records showing territory and expiry checks operating as blocking conditions.
- Audit results with mismatch dispositions and closure dates.
- UGC permission records and generated-content provenance entries for sampled assets.

## Failure modes and correction

Common failures include a stock clip used in paid media under an editorial-only license, music licensed for one territory trafficked worldwide, a talent contract covering one year of digital use silently entering year three, a campaign re-using last year's hero image after its term lapsed, fonts installed beyond seat counts as the team grew, UGC reposted from a platform with no recorded permission, and an agency's library assets entering the brand library with no manifest at handover. The structural failure is scope drift: each reuse seems continuous with the last, until the intersection of licenses no longer covers the current use.

Correction starts with withdrawal from out-of-scope placements, executed against the takedown list, with caches and partner syndication included. The scope gap is remediated either by renewal and extension, by replacement of the asset, or by ending the placement; the choice is recorded with rationale. Where out-of-scope use exposed the organization to licensor claims, escalation follows the contractual notice path rather than quiet removal. Agency handovers require manifest transfer as an acceptance criterion. Recurrence tightens the trafficking checks and shortens the audit interval for the failing asset class.

## Limitations

A manifest proves what was recorded, not what was agreed; contracts ambiguous about media classes or territory leave the manifest uncertain until renegotiated. Rights under foreign law, collective licensing regimes for music, and platform-specific content rules add layers this control references but does not resolve. Generated-media rights are unsettled and evolving, so manifest entries there are provisional by nature. The manifest does not substitute for legal review of high-value acquisitions, and its computed scopes are only as good as the fields entered at intake.

## Canonical sources

- **Primary authority 1 — WIPO-administered Berne Convention for the Protection of Literary and Artistic Works (WIPO Lex text):** [https://www.wipo.int/wipolex/en/text/283698](https://www.wipo.int/wipolex/en/text/283698)
- **Primary authority 2 — WIPO, Copyright topic hub (rights, licensing and related rights overview):** [https://www.wipo.int/copyright/en/](https://www.wipo.int/copyright/en/)
- **Reference — U.S. Copyright Office, Circular 56, Copyright Terminology (licensing basics):** [https://www.copyright.gov/circs/circ56.pdf](https://www.copyright.gov/circs/circ56.pdf)
