# Marketing Disclosure Placement Design

A disclosure that a reasonable consumer does not notice is functionally absent. This article governs where disclosures are placed and how they are made noticeable across the devices and surfaces on which marketing actually renders: desktop pages, mobile screens, small-format ads, social feeds, video, and audio. The design standard is clear and conspicuous: the disclosure must be unavoidable at the moment the claim it qualifies is consumed, on the device the consumer is actually using, not merely present somewhere in the artifact. Placement decisions that look acceptable in a desktop review environment routinely fail on the phone where most impressions occur.

## Scope

This control applies to material disclosures attached to marketing communications: paid-placement labels, material-connection disclosures, offer-condition qualifications, pricing footnotes, health and safety caveats, and any statement whose absence would change the net impression of the message. It covers placement, proximity, prominence, and the rendering conditions under which the disclosure survives, across responsive web pages, mobile applications, ad units of constrained size, email, social posts, short video, and audio formats.

It does not decide what must be disclosed; that determination belongs to claim review and endorsement controls. Its question is purely presentational: assuming the disclosure is required and correctly worded, does its placement make it effective?

## Workflow or implementation guidance

1. **Start from the claim's location, not the layout's leftover space.** For each material claim, record the surface region where the claim appears. The disclosure is then designed to sit within the same region or as close as the medium allows; a footer several screens away does not qualify as proximate to a hero-panel claim.
2. **Design mobile-first for constrained canvases.** The smallest intended canvas is designed first. If the disclosure cannot be made noticeable within the ad unit or viewport where the claim appears, the claim is shortened, moved, or dropped, rather than pushing the disclosure behind an expandable control or a "more" link that most users will never open.
3. **Assign prominence attributes explicitly.** Each disclosure spec records size relative to surrounding text, color contrast against the actual background, weight, duration on screen for video, and volume relative to narration for audio. Vague instructions such as "make it legible" are replaced with measurable values.
4. **Handle scroll, truncation, and interstitial behavior.** Disclosures affected by truncation are tested in the truncated state; ellipsis that hides half a disclosure is a failure. Scroll-triggered disclosures must appear before the consumer can act on the claim, not after the conversion button.
5. **Keep the disclosure attached through syndication.** When content is embedded, shared, or republished by partners, the disclosure travels with the content fragment. A disclosure that renders only on the original page but not in the embeddable card is treated as missing on the syndicated surface.
6. **Test on real devices under realistic conditions.** Review covers the actual phone models, screen sizes, night mode, browser reader modes, and slow-connection renderings that materially affect noticeability, not only a desktop preview at full width.
7. **Re-verify on template change.** Any change to the template, theme, or ad format that hosts a disclosure re-triggers the placement review, because layout changes are the most common cause of a previously effective disclosure being pushed below the fold.

## Controls

- Every campaign artifact carries a disclosure map: claim, required disclosure, wording version, placement coordinates or template slot, and prominence spec.
- Placement approvals are recorded against named device profiles; a profile set is retired and re-approved when the device mix shifts materially.
- Automated layout tests assert that disclosure elements are within the initial viewport of the claim's container and meet contrast thresholds; failures block publication of the template.
- Ad-network format constraints that cannot host a required disclosure trigger a format decision, never a disclosure deletion; the ad runs in a different format or not at all.
- Audio and video disclosures are scripted with explicit duration and placement within the timeline, and reviewed against the accompanying visual.
- Platform-mediated surfaces where the brand controls only part of the card are documented as shared-control, with the disclosure responsibilities of each party recorded.

## Validation evidence

- Device captures of each final artifact on the approved device set, showing claim and disclosure in the same frame or documented proximity.
- The disclosure map with wording versions and placement decisions, signed by the reviewer.
- Layout test output asserting viewport placement and contrast for every published template.
- For video and audio: the timeline showing disclosure placement, plus a viewing or listening transcript confirming the disclosure is delivered before the call to action it qualifies.
- Syndication spot checks confirming the disclosure survives in embedded and shared renders.
- Change records demonstrating that template updates re-triggered placement review.

## Failure modes and correction

Recurring failures include a "terms apply" link in a color barely distinguishable from the background, a material-connection disclosure placed in a profile bio that the viewer of a shared post never visits, pricing conditions placed below a purchase button on mobile, a disclosure hidden behind a hover state that has no touch equivalent, captions disabled by default carrying the only qualification in a video, and a responsive redesign that preserved the disclosure markup but moved it beneath three screens of imagery. The shared root cause is that disclosure effectiveness is judged in the authoring environment rather than the consumption environment.

Correction requires fixing the placement, not the wording alone: the disclosure is moved into effective proximity and re-captured on the device set before the artifact returns to circulation. Where a defective placement ran in market, the exposure window is quantified and the correction decision, including whether follow-up communication to affected consumers is needed, is escalated rather than treated as a design ticket. Repeated failures from template changes trigger mandatory disclosure regression checks in the release pipeline.

## Limitations

Noticeability is ultimately judged by consumer perception, and no fixed rule guarantees effectiveness in every context; the placement values here are conservative defaults, not safe harbors. Platform constraints can change without notice, and surfaces the brand does not control may strip or degrade disclosures despite correct implementation. This control does not resolve wording quality, translation adequacy, or the substantive question of whether a connection or condition is material; it assumes those determinations arrive as inputs. Accessibility requirements add independent obligations beyond deceptive-practices concerns.

## Canonical sources

- **Primary authority 1 — Federal Trade Commission, .com Disclosures: How to Make Effective Disclosures in Digital Advertising:** [https://www.ftc.gov/business-guidance/resources/com-disclosures-how-make-effective-disclosures-digital-advertising](https://www.ftc.gov/business-guidance/resources/com-disclosures-how-make-effective-disclosures-digital-advertising)
- **Primary authority 2 — Federal Trade Commission, Disclosures 101 for Social Media Influencers:** [https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers](https://www.ftc.gov/business-guidance/resources/disclosures-101-social-media-influencers)
- **Reference — W3C, Web Content Accessibility Guidelines (WCAG) 2.2, contrast and readability:** [https://www.w3.org/TR/WCAG22/](https://www.w3.org/TR/WCAG22/)
