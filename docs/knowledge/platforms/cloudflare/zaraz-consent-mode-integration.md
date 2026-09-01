# Zaraz Consent Mode Integration

Zaraz runs third-party tools from the edge, which means the decision to fire a tool can be made centrally rather than scattered through page JavaScript. Consent mode uses exactly that: a consent management layer that gates whether and how tools run, so analytics and marketing scripts respect the visitor's choice without each vendor needing its own consent plumbing. The integration work is twofold — wiring the consent tool's triggers to the visitor's saved preferences, and gating each tool's events on the consent states those preferences produce. Done right, a declined analytics cookie is not merely hidden from the page; the corresponding tool never receives the event at all.

## Scope

Covers integrating Zaraz consent management with the Zaraz tool chain: configuring the consent tool, mapping consent answers to consent-mode states, gating individual tools and their triggers, and verifying event gating end to end. Applies to sites running Zaraz with a consent banner or consent management platform. Excludes the design of the consent banner UI, jurisdiction-specific legal advice, and Zaraz's server-side integrations beyond their consent gating behavior.

## Workflow or implementation guidance

1. Inventory the tools loaded through Zaraz and classify each by consent dependency: strictly necessary (no gating), analytics (fires only on analytics consent), marketing (marketing consent), and preference-type tools with their own state. Every tool must land in exactly one class.
2. Enable consent management in Zaraz and configure the consent tool (Zaraz's built-in consent component or the connected consent management platform). The consent tool is what captures and stores the visitor's answer.
3. Map consent answers to consent mode states. Consent mode distinguishes whether consent exists at all and, where regional granularity is used, whether events are withheld entirely or sent with limited signals. Decide per region which default applies before any interaction.
4. Gate each tool at the tool level first: in the tool's consent settings, bind it to the consent categories it depends on, so the tool does not initialize when its category is unset or denied.
5. Gate at the trigger level for finer control: a trigger that fires a marketing conversion event can be conditioned on marketing consent even if the parent tool has broader permissions. Set tool-level gates as the floor and trigger-level conditions as refinements.
6. Add a consent-change path: when the visitor updates their answer, the saved consent state must update and downstream gating must follow on subsequent events. Test the update flow, not only the first-visit flow.
7. Verify gating end to end with a network-inspection test per class: decline all, accept all, and accept selectively, confirming in each state which tool requests and event transmissions actually occur.
8. Keep the mapping current: every new tool added to Zaraz gets its consent class assigned before its first production event, through the same classification step.

## Controls

- Tool classification register: every Zaraz tool carries a consent class, an owner, and a review date.
- No-default-fire rule: tools without an assigned consent class cannot ship; strictly necessary tools are labeled as such explicitly rather than left unset.
- Regional defaults documented: each supported region's pre-interaction default state is recorded and reviewed against current requirements.
- Consent-change regression test: automated or scripted checks that updating consent changes subsequent event firing.
- Network-level gating evidence: per-class request maps captured for decline-all, accept-all, and selective states.
- New-tool gate: adding a tool to Zaraz without consent configuration is a blocked change.

## Validation evidence

- Tool classification register export from the Zaraz configuration showing classes per tool.
- Consent state mapping configuration as deployed, including regional defaults.
- Network captures or request logs for the three test states (decline all, accept all, selective) showing exactly the expected tool endpoints contacted.
- Consent-change test transcript: preference update followed by events that respect the new state.
- Trigger-level condition listing for triggers with consent refinements beyond tool-level gates.
- Review sign-off dates per tool class from the register.

## Failure modes and correction

- Tool fires before consent because it initializes on page load regardless of state: the tool-level gate was not bound; rebind the tool to its consent categories and re-verify with network capture.
- Consent updated but events still follow the old state: the consent-change path did not propagate; confirm the consent tool saves and the gate reads current state on each event evaluation.
- A trigger-level refinement was assumed to gate the tool entirely: trigger conditions only constrain that trigger; a missing tool-level gate leaves other triggers open. Set both deliberately.
- Regional defaults fire analytics in a region requiring opt-in: correct the region's default state and re-run the decline-all test from that region's vantage.
- New tool shipped without classification: blocked by the new-tool gate; assign the class and backfill the register.
- Consent banner itself fails to load, leaving defaults in force: monitor banner load success rate; if the banner cannot load, the conservative default governs — verify the default direction is the conservative one.

## Limitations

- Consent gating governs tools and events orchestrated by Zaraz; scripts loaded outside Zaraz must be gated separately.
- Consent mode states transmitted to vendors depend on each vendor's support for those signals.
- Regional granularity is as good as the region configuration; visitors via proxies or misclassified regions follow the configured default.
- Verification through network inspection reflects tested states; vendor-side processing of limited-signal events is outside direct observation.
- Legal adequacy of the consent flow is a compliance question beyond this technical integration.

## Canonical sources

- Cloudflare Zaraz docs, "Consent management": https://developers.cloudflare.com/zaraz/consent-management/
- Cloudflare Zaraz docs section index: https://developers.cloudflare.com/zaraz/
