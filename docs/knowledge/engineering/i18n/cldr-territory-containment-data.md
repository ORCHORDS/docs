# CLDR Territory Containment Data in Locale Reasoning

Territory containment is the CLDR data model that organizes world territories into nested groupings such as subcontinents, continents, and economic or political groupings like the European Union. Applications consult it whenever behavior must escalate from a specific territory to a sensible superset: fallback content selection, regional preference aggregation, and filtering catalogs by region. This article covers how the containment graph is structured in CLDR, how to consume it correctly from tooling, and the failure modes that appear when teams treat containment as a simple parent pointer instead of a directed multigraph.

## Scope

This article addresses the `territoryContainment` element of CLDR supplemental data as specified in Part 1 of UTS #35. It covers the structure of the containment graph, its use in territory grouping and fallback logic, and validation of containment-derived behavior. It does not cover territory subdivisions ( subdivisionsContainment versus subdivision containment), time-zone-to-territory mapping, or likely-subtags reasoning except where containment interacts with them.

## Workflow or implementation guidance

The `territoryContainment` structure maps a grouping territory code (for example `001` for the world, `019` for the Americas, `155` for Western Europe) to a list of contained territories, each recorded with a `contains` attribute. A single territory can appear under multiple groupings because groupings serve different purposes: geographic (continent), geopolitical (European Union `EU`), and currency or trade unions (eurozone `EZ`). Any code that walks containment must therefore treat the data as a directed graph with multiple parents, not a tree.

A typical consumption workflow has four steps:

1. Resolve the grouping codes you care about from the CLDR root supplemental data file `supplementalData.xml`, filtering to `territoryContainment` group elements.
2. Build an adjacency map from grouping code to contained codes. Preserve the `status` attribute when present, because groupings can carry a status such as `deprecated` for territories like `AN` (Netherlands Antilles), which was dissolved and whose members were reassigned in later CLDR releases.
3. For a user territory, compute the set of ancestors by traversing upward through every grouping that lists it. Cache the result keyed by CLDR version, because containment edges shift between releases as territories gain or lose membership (Brexit moved `GB` out of the `EU` grouping in CLDR 38).
4. When selecting content, prefer exact territory match, then the smallest grouping that both contains the territory and has content, then progressively larger groupings up to `001`.

For example, a storefront resolving `fr-CH` (French as used in Switzerland) might have no Swiss-French catalog entry. Walking containment, Switzerland (`CH`) sits under `155` (Western Europe), then `39` (Europe), then `150` (Europe), then `001`. The storefront can prefer a Western Europe promotion over a world promotion. The same traversal must not stop at the first ancestor: eurozone membership (`EZ`) is irrelevant to language fallback but critical to payment-method configuration, so the consumer decides which groupings participate in each decision rather than letting the data model imply a single hierarchy.

Two properties of the data deserve explicit handling. First, grouping codes use the UN M49 numeric range (`001`–`999`), which does not collide with ISO 3166-1 alpha-2 territory codes, so a code-length check distinguishes them mechanically. Second, containment edges are declarative snapshots; they encode membership at publication time and carry no effective-dating metadata beyond the element status attributes, so historical questions ("was `GB` in `EU` for a 2019 report?") require pinning the CLDR version used at report time.

## Controls

- Pin the CLDR version in dependency manifests (for ICU-backed stacks, the ICU version implies the CLDR version) so containment edges are reproducible across build environments.
- Reject unknown grouping codes at load time with a startup check comparing loaded grouping codes against a frozen list derived from the pinned CLDR release; a mismatch indicates the data file and code expectations have drifted.
- Treat containment traversal results as immutable derived data: build once per CLDR version, expose read-only maps, and never mutate ancestor sets at runtime.
- Log the grouping codes consulted for every fallback decision at debug level, including the CLDR version identifier, so support engineers can reconstruct why a user in `CH` received Western Europe content instead of a world default.
- When groupings carry a `status` attribute, exclude deprecated groupings from fallback chains unless an explicit opt-in flag is set, and record the opt-in in the decision log.

## Validation evidence

- The `territoryContainment` element, its `contains` attribute, and the grouping code conventions are defined in UTS #35 Part 1, Localized Common Data, published by the Unicode Consortium.
- The CLDR supplemental data downloads page documents the structure of `supplementalData.xml` and the release process that updates containment membership, including the CLDR 38 change that removed `GB` from the `EU` grouping after Brexit.
- A practical verification is to load two pinned CLDR releases and diff the containment edges for a handful of politically mobile territories (`GB`, `CH`, `GR`): the diff is non-empty between CLDR 37 and CLDR 38 precisely for `EU` membership, confirming the data is version-sensitive rather than static.

## Failure modes and correction

- **Single-parent assumption.** Code that assigns each territory exactly one parent silently drops alternative groupings. The symptom is correct continent-level fallback but wrong eurozone or EU-specific behavior. Correct by traversing all parents and carrying the full ancestor set into each decision.
- **Stale CLDR version.** Deployments that bundle an old ICU or CLDR artifact continue to report dissolved territories (`AN`, `CS`) as valid groupings. Correct by upgrading the pinned version and adding a startup assertion that deprecated codes are absent from the active map.
- **Confusing grouping codes with territory codes.** Length-based checks work, but code that naively uppercases or normalizes codes can turn `001` into `1` and lose the edge. Correct by validating codes against the M49 numeric range at load time.
- **Fallback chain caching by user locale instead of territory.** Caching on the full locale tag (`fr-CH`) multiplies cache entries and hides the fact that containment is territory-scoped. Correct by keying the cache on territory and CLDR version only.
- **Assuming containment implies preference ordering.** The graph says what contains what, not which grouping is more relevant; relevance is a product decision. Correct by making the grouping priority an explicit configuration list rather than inheriting traversal order.

## Limitations

- Containment data carries no temporal dimension: it cannot answer when a membership changed, only what the pinned release says now.
- Economic and political groupings (EU, eurozone) reflect CLDR's editorial snapshot and may lag real-world changes by one or more releases.
- The graph does not weight edges; proximity or similarity between territories must come from other CLDR data such as language matching tables.
- Consumers needing subdivision-level grouping (states, provinces) must use subdivision containment data, which follows a different element and is out of scope here.

## Canonical sources

- Unicode Consortium, UTS #35: Unicode Locale Data Markup Language (LDML), Part 1: Localized Common Data — territory containment: https://unicode.org/reports/tr35/
- Unicode Consortium, CLDR — Common Locale Data Repository project and release downloads: https://cldr.unicode.org/
