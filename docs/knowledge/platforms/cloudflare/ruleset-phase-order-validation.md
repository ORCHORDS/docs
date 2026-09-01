# Ruleset Phase Order Validation

Cloudflare products built on the Ruleset Engine — URL redirects, transform rules, WAF custom rules, rate limiting, cache settings — do not run in arbitrary order. Each executes in a named phase of the request lifecycle, and the phases execute in a fixed sequence: for example, URL rewrite rules in their phase see the request after certain earlier phases have already altered or decided things, and a WAF custom rule evaluating `http.request.uri.path` sees whatever transformations earlier phases have applied. Most ruleset bugs that look like "my rule didn't fire" or "the field had the wrong value" are actually phase-order misunderstandings. Phase order validation is the practice of stating, before deploy, which phases a configuration spans and what request state each rule will see — then proving it with crafted requests.

## Scope

Covers validating expectations about ruleset phase ordering for multi-product configurations: when rules in different products interact, how to determine the effective evaluation order, and how to test that a rule sees the request state its author assumed. Applies to zones combining two or more Ruleset Engine products in a single request path. Excludes single-product rule authoring (covered in the custom rules expression budget article), Workers-based routing, and load balancer decision order.

## Workflow or implementation guidance

1. Enumerate every product in the request path for the surface being changed: transforms, redirects, WAF custom rules, rate limiting, cache rules, compression, custom error rules. Each contributes one or more phases.
2. Map each to its phase using the published phases list, and write down the expected execution order for your specific combination. If two products' relative order is load-bearing for behavior, that dependency goes in the record explicitly — for instance, "the WAF rule must see the post-redirect path" or "must see the pre-transform path".
3. For each rule that reads a mutable field (URI path, query, headers), annotate which version of the field it expects: original request or as modified by an earlier phase. This annotation is the core of the validation artifact.
4. Derive test cases from the annotations: craft request pairs that differ only in the input an earlier phase would change, and confirm the downstream rule's match behavior distinguishes them exactly as annotated.
5. Stage the combined configuration (where staging is available) or deploy to a low-traffic test hostname first, and execute the crafted pairs against it, recording outcomes versus expectations.
6. Where a dependency cannot be satisfied by ordering alone — the engine's phase sequence is fixed and not user-reorderable — restructure the rules: move the logic into the earlier phase's own product, duplicate a condition, or accept and document the constraint.
7. Freeze the phase-dependency map in the change record, and re-validate whenever a new product is added to the path or a rule's field usage changes, since both can silently invalidate prior annotations.

## Controls

- Phase map requirement: changes spanning two or more ruleset products include a written phase-order map before review.
- Field-version annotation rule: every rule reading a mutable field states which version it expects, original or transformed.
- Crafted-pair testing gate: order-sensitive expectations are proven with request pairs in staging or on a test hostname before production.
- No reordering assumption: configurations never assume phases can be reordered; dependencies are resolved by restructuring, documented as such.
- Change-triggered revalidation: adding a product to the path or changing a rule's field inputs re-opens the phase map.
- Dependency register: known order-sensitive rule pairs are listed with their expected interaction, checked during revalidation.

## Validation evidence

- The phase-order map for the affected surface, naming each product's phase and the expected sequence.
- Field-version annotations for all order-sensitive rules.
- Crafted request pair results: each pair, the expected versus observed match or action outcome, from staging or the test hostname.
- The change record including the frozen map and the validation outcome.
- Dependency register entries for order-sensitive pairs discovered or confirmed.
- Revalidation records triggered by later path changes, with deltas against the prior map.

## Failure modes and correction

- A WAF or later rule sees the original URI although the author assumed the rewritten one: the transform phase runs later than assumed (or vice versa); fix by moving the logic into the product that owns the needed state, or restructure per the fixed phase sequence.
- A redirect fires before a security rule that needed to evaluate the original request: reorder expectations — the engine's sequence is fixed; either evaluate in the earlier phase or duplicate the condition so both paths are covered.
- Two rules in the same phase conflict, and the first match wins unexpectedly: consolidate or make the expressions mutually exclusive; same-phase conflicts are ordering issues internal to the ruleset, not phase bugs.
- Validation passed in staging but production behaves differently: check for zone-level versus account-level ruleset differences and hostname-specific rules; re-run the crafted pairs against production with log actions.
- Documentation drift: a product's phase or field semantics changed under you; revalidation on product additions exists precisely to catch this — also re-check after major product updates.
- The map was never written because "it's just one rule": the control triggers on any multi-product path change; a single new rule in a second product still requires the map.

## Limitations

- Phase order is defined by the Ruleset Engine and cannot be customized per zone.
- The phases list evolves as products are added; maps carry a date and must be re-derived against current documentation.
- Crafted-pair testing proves the tested cases; interactions with untested product combinations may still surprise.
- Some products run their logic at stages with limited visibility, making black-box validation the practical method.
- Account-level and zone-level rulesets both contribute phases; the map must include both scopes to be complete.

## Canonical sources

- Cloudflare Ruleset Engine docs, "Phases list": https://developers.cloudflare.com/ruleset-engine/reference/phases-list/
- Cloudflare Ruleset Engine docs, "Reference": https://developers.cloudflare.com/ruleset-engine/reference/
