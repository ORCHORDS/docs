# Helm Library Chart Composition

**Issue:** Application teams that duplicate boilerplate across many Helm charts accumulate technical debt that makes coordinated upgrades painful, while library charts that are too generic fail to capture the operational conventions that bind a platform together. The composition pattern requires explicit decisions about what belongs in a library, what stays in the consumer chart, and how values flow between layers so that a single version bump can propagate predictably.

**Date:** 2026-08-15
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## What A Library Chart Actually Is

A library chart is a Helm chart of type `library` whose only payload is named templates, helper functions, and value defaults. Helm refuses to install or render a library chart on its own; it can only be referenced as a dependency from another chart. The dependency declaration goes in `Chart.yaml` under `dependencies`, with the version range specified in semver terms. When the parent chart is rendered, Helm pulls in the library templates and executes them in the parent's value context.

This indirection lets platform teams define opinionated defaults once and lets application teams override only the values that diverge from those defaults. The composition must be governed explicitly; otherwise it becomes a tangle of implicit overrides that no one understands. A working pattern is to define a small number of named override hooks in the library and treat all other values as immutable defaults for that release.

## Designing The Value Surface

The library chart's values.yaml is its public API. Treat it with the same rigor as a software SDK: every key is a contract, deprecations follow semver, and breaking changes require a major version bump. The library should expose the smallest possible value surface that still captures the platform's commonality. Defaults that are merely "what we usually pick" should not be in the library; they belong in the application chart as opinionated overrides.

Values that are environment-specific (cluster name, region, certificate authority) should be passed through to the library as a single nested map rather than as top-level keys. This makes the boundary obvious and reduces the chance that an application chart accidentally redefines a default that the platform team thought was controlled. The library can document its expected keys with a JSON schema embedded in the chart; Helm supports this via the `schema.json` file.

## Templates That Compose Well

Library templates should accept a named value object and produce a small, composable manifest fragment. Avoid templates that emit multiple resource kinds from a single helper, because consumers cannot pick and choose the fragments they want. Good library templates look like `myplatform.monitoring.servicemonitor` and return a single ServiceMonitor manifest. Good consumers stitch several of these fragments together with named templates that read like a sentence.

Helper functions in the library should be pure. Mutating a global value object inside a helper is a common mistake that produces surprising behavior when the chart is rendered multiple times in the same release. Treat the value object as immutable from the template's perspective; if a helper needs to compute a derived value, return it and let the caller assign the result.

## Versioning And Upgrade Strategy

Library charts follow strict semver because they have many consumers. A patch release must not change any rendered output for a consumer that has not updated its dependency version. A minor release may add new template helpers and new value keys but must not rename or remove existing keys. A major release may reorganize, but the platform team must publish a migration guide and a compatibility shim that works for at least one minor cycle so consumers can move gradually.

The dependency declaration should pin to an exact version for production consumers and accept ranges only in development. Helm resolves ranges at fetch time, and the resolution result is stored in `requirements.lock` or `Chart.lock`. Commit the lock file and treat any drift between the lock file and the resolved chart as a release blocker. This is the only way to guarantee that a deployment environment sees the exact same library version as CI did.

## Failure Modes

The most common composition failure is treating the library chart as a dumping ground, so the library becomes a kitchen-sink dependency that bundles many irrelevant resources into every consumer release. The mitigation is strict ownership: a library chart should be owned by the platform team, and adding a helper requires a change request that the team evaluates against existing helpers.

A second failure is silent override of library defaults by consumer values that have the same key but different semantics. Library authors should namespace their values with a top-level key (for example `platform.monitoring.*`) so consumers cannot accidentally collide with the library's internal value structure. Without this namespace, an application chart that uses `serviceAccount.name` for its own purposes will collide with a library that also reaches into `serviceAccount.name`.

A third failure is missing `dependencies` declaration in the consumer `Chart.yaml`, which causes `helm template` to fail at parse time but only after a CI build has invested several minutes in unrelated work. Lint rules should require that every consumer chart includes a `dependencies` block whose `repository` and `version` resolve to a known library in the platform's own registry, with the dependency tree flattened at build time to detect circular references early.

## Canonical sources

1. https://helm.sh/docs/v3/chart_types/library/
2. https://helm.sh/docs/v3/chart_best_practices/dependencies/