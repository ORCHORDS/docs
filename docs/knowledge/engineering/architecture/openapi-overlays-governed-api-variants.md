# Governed OpenAPI overlays for API variants

**Issue:** Forking a base OpenAPI description for each customer, environment, or publication audience creates incompatible contracts that drift silently. OpenAPI Overlays provide a separate, declarative change layer, but only when the base specification remains authoritative and overlay application is reproducible.

**Date:** 2026-08-17
**Repo:** example-org/example-repo
**Author:** ORCHORDS
**Status:** published

## The model

An Overlay document targets elements of an OpenAPI Description with JSONPath and applies actions such as updates or removals. It is a transformation input, not a replacement API contract.

1. **Keep one canonical base.** The base OpenAPI document defines the service contract. Place audience-specific documentation, gateway metadata, or publication redactions in a named overlay rather than copy the base file.
2. **Name the target and purpose.** An overlay must identify the source specification and state whether it is for public documentation, a partner portal, an environment, or a generated client. Do not use one ambiguous “production” overlay for unrelated audiences.
3. **Apply overlays deterministically.** Pin the overlay specification/tool version, run transformations in CI, and publish both the source inputs and generated output as build artifacts.
4. **Validate the rendered contract.** Lint and validate the transformed OpenAPI document, then run compatibility/consumer checks against the result. A valid base does not prove a valid transformed output.
5. **Treat removal as a publication decision.** Removing an operation from public documentation does not remove the live endpoint or its authorization risk. The gateway and service must enforce the actual boundary.

## Safe workflow

1. Review base-spec changes and overlay changes independently.
2. Generate every supported variant in CI.
3. Diff each generated variant against its prior approved output.
4. Fail if an overlay points to no target or unexpectedly changes a protected API area.
5. Publish the generated artifact with a source/overlay revision reference.
6. Retire an overlay when its variation becomes a stable property of the canonical contract.

## Failure modes

- **Forking instead of overlaying:** fixes land in one contract but not another.
- **Using overlays as runtime authorization:** documentation transformation is not access control.
- **Unvalidated JSONPath selectors:** a broad selector can alter more operations than intended; a stale selector can alter none.
- **Generating only locally:** consumers see a different contract than CI reviewed.
- **Environment secrets inside descriptions:** overlays are version-controlled text; never place credentials, tokens, or private endpoints in them.

## Sources

- [OpenAPI Overlay Specification](https://github.com/OAI/Overlay-Specification)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)
